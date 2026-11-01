import {useEffect,useRef,useState,type RefObject} from 'react';
export default function ReferencePreview({html,width,height,frame}:{html:string;width:number;height:number;frame:RefObject<HTMLIFrameElement|null>}){
 const container=useRef<HTMLDivElement>(null),[scale,setScale]=useState(1);
 useEffect(()=>{const element=container.current;if(!element)return;const observer=new ResizeObserver(()=>{setScale(Math.max(.1,Math.min(1,(element.clientWidth-24)/width,(element.clientHeight-42)/height)));});observer.observe(element);return()=>observer.disconnect();},[width,height]);
 return <div className="reference-preview" ref={container}><div className="reference-size">设计视口 {width} × {height} · 缩放 {Math.round(scale*100)}%</div><div style={{width:width*scale,height:height*scale,flexShrink:0}}><iframe title="生成应用预览" ref={frame} sandbox="allow-scripts allow-forms" srcDoc={html} style={{width,height,transform:`scale(${scale})`,transformOrigin:'top left',border:0,display:'block'}}/></div></div>
}
