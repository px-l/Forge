"""UIProof stdio MCP adapter. One SSH session owns a job and its loopback tunnel."""
import asyncio
import base64
import json
import os
import secrets
import tempfile
from contextlib import asynccontextmanager
from urllib.parse import urlsplit
from .design import design_viewport

_lock = asyncio.Lock()


class UIProofError(RuntimeError):
    pass


class MCP:
    def __init__(self, process):
        self.process = process
        self.sequence = 0
        self.logs = bytearray()
        self.drain = asyncio.create_task(self._stderr())

    async def _stderr(self):
        while chunk := await self.process.stderr.read(4096):
            self.logs.extend(chunk)
            del self.logs[:-8192]

    async def request(self, method, params):
        self.sequence += 1
        mid = self.sequence
        self.process.stdin.write((json.dumps({'jsonrpc':'2.0','id':mid,'method':method,'params':params})+'\n').encode())
        await self.process.stdin.drain()
        while True:
            line = await asyncio.wait_for(self.process.stdout.readline(), 60)
            if not line:
                raise UIProofError('UIProof SSH 连接已关闭：'+self.logs.decode(errors='replace')[-1000:])
            message = json.loads(line)
            if message.get('id') != mid:
                continue
            if 'error' in message:
                raise UIProofError(str(message['error']))
            return message['result']

    async def start(self):
        await self.request('initialize', {'protocolVersion':'2024-11-05','capabilities':{},'clientInfo':{'name':'forge-delivery','version':'0.1'}})
        self.process.stdin.write(b'{"jsonrpc":"2.0","method":"notifications/initialized"}\n')
        await self.process.stdin.drain()

    async def tool(self, name, args):
        result = await self.request('tools/call', {'name':name,'arguments':args})
        content = '\n'.join(x.get('text','') for x in result.get('content',[]) if x.get('type')=='text')
        if result.get('isError'):
            raise UIProofError(content)
        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            raise UIProofError('UIProof 返回非结构化结果') from e

    async def close(self):
        if self.process.returncode is None:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), 5)
            except asyncio.TimeoutError:
                self.process.kill()
                await self.process.wait()
        await self.drain


async def code_tree(html):
    """Actual Git tree of the delivered single-file application, not a fabricated digest."""
    with tempfile.TemporaryDirectory(prefix='forge-tree-') as directory:
        async def git(*args, data=None):
            p=await asyncio.create_subprocess_exec('git','--git-dir='+directory,*args,stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
            out,err=await p.communicate(data)
            if p.returncode:raise UIProofError('无法生成交付代码 Git tree：'+err.decode()[:300])
            return out.decode().strip()
        await git('init','--bare','--quiet')
        blob=await git('hash-object','-w','--stdin',data=html.encode())
        return await git('mktree',data=f'100644 blob {blob}\tindex.html\n'.encode())


@asynccontextmanager
async def preview_server(html):
    token=secrets.token_urlsafe(24)
    body=html.encode()
    async def handle(reader,writer):
        try:
            request=await asyncio.wait_for(reader.readuntil(b'\r\n\r\n'),5)
            parts=request.split(b'\r\n',1)[0].decode().split(' ')
            ok=len(parts)==3 and parts[0]=='GET' and urlsplit(parts[1]).path=='/'+token
            payload=body if ok else b'Not found'
            headers=(f'HTTP/1.1 {"200 OK" if ok else "404 Not Found"}\r\nContent-Type: text/html; charset=utf-8\r\nContent-Length: {len(payload)}\r\nCache-Control: no-store\r\nContent-Security-Policy: default-src \'none\'; script-src \'unsafe-inline\'; style-src \'unsafe-inline\'; img-src data:; connect-src \'none\'; form-action \'none\'; frame-src \'none\'\r\nConnection: close\r\n\r\n').encode()
            writer.write(headers+payload)
            await writer.drain()
        except (TimeoutError,asyncio.IncompleteReadError,ConnectionError):
            pass
        finally:
            writer.close()
            await writer.wait_closed()
    server=await asyncio.start_server(handle,'127.0.0.1',0)
    try:yield server.sockets[0].getsockname()[1],token
    finally:server.close();await server.wait_closed()


async def verify(state):
    target=state.get('target','')
    if not target.startswith('data:image/') or ';base64,' not in target:
        raise UIProofError('UIProof 需要已确认的目标效果图')
    baseline=target.split(';base64,',1)[1]
    try:base64.b64decode(baseline,validate=True)
    except ValueError as e:raise UIProofError('目标效果图编码无效') from e
    if len(baseline)>8*1024*1024:raise UIProofError('UIProof 目标图片超过8MB限制')
    viewport=design_viewport(target)
    tree=await code_tree(state['html'])
    context={'taskId':state['task_id'],'prototypeId':state['design_id'],'tree':tree}
    port=int(os.getenv('UIPROOF_TUNNEL_PORT','49317'))
    async with _lock, preview_server(state['html']) as (local_port,token):
        command=['ssh','-T','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ExitOnForwardFailure=yes','-o','ConnectTimeout=15','-o','ServerAliveInterval=15','-R',f'127.0.0.1:{port}:127.0.0.1:{local_port}',os.getenv('UIPROOF_SSH_HOST','yun2'),os.getenv('UIPROOF_REMOTE_COMMAND','/opt/uiproof/bin/mcp')]
        process=await asyncio.create_subprocess_exec(*command,stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE,limit=40*1024*1024)
        mcp=MCP(process)
        try:
            async with asyncio.timeout(int(os.getenv('UIPROOF_TIMEOUT','180'))):
                await mcp.start()
                job=await mcp.tool('uiproof_verify_image',{'baselineBase64':baseline,'config':{'url':f'http://127.0.0.1:{port}/{token}?forge_capture=1','viewport':viewport},'context':context})
                while True:
                    status=await mcp.tool('uiproof_status',{'jobId':job['jobId']})
                    if status['status']=='error':raise UIProofError(status.get('error','UIProof 任务失败'))
                    if status['status']=='complete':break
                    await asyncio.sleep(.5)
                run_id=status['runId']
                result=await mcp.tool('uiproof_result',{'runId':run_id})
                if result.get('clientContext')!=context:raise UIProofError('UIProof 结果与当前代码或设计版本不匹配')
                issues=[]
                for item in result.get('states',[]):
                    page=await mcp.tool('uiproof_issues',{'runId':run_id,'state':item['name'],'offset':0,'limit':20})
                    issues.extend([{'state':item['name'],**i} for i in page.get('issues',[])])
                report=await mcp.tool('uiproof_report',{'runId':run_id})
                if result['status']=='error':raise UIProofError('UIProof 捕获或比较失败：'+json.dumps(result.get('states',[]),ensure_ascii=False)[:1000])
                return {'provider':'uiproof','passed':result['status']=='passed','run_id':run_id,'context':context,'viewport':viewport,'states':result.get('states',[]),'issues':issues,'report_html':report['html']}
        except TimeoutError as e:
            raise UIProofError('UIProof 验证超时，未判定为通过；可从检查点重试') from e
        finally:
            await mcp.close()
