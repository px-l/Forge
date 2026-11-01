"""Explicit remote smoke test: sends synthetic demo HTML/reference only."""
import asyncio
from pathlib import Path
from backend.uiproof import verify
from backend.sample import SAMPLE_HTML, SAMPLE_TARGET
async def main():
    result = await verify({'html':SAMPLE_HTML,'target':SAMPLE_TARGET,'task_id':'forge-integration-smoke','design_id':'demo-reference'})
    Path('docs').mkdir(exist_ok=True)
    Path('docs/uiproof-smoke.html').write_text(result.pop('report_html'))
    print({k:result[k] for k in ('provider','run_id','passed','context')})
    assert result['provider']=='uiproof'
    assert result['states']
    # Intentionally different design: completion must not become a false pass.
    assert result['passed'] is False
asyncio.run(main())
