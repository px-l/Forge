"""Shared, validated design contract for image generation, HTML and verification."""
import re
from pydantic import BaseModel, Field
from typing import Literal


class Section(BaseModel):
    id: str = Field(pattern=r'^[a-z][a-z0-9-]{0,30}$')
    label: str = Field(max_length=80)
    columns: int = Field(default=1,ge=1,le=4)


class Spec(BaseModel):
    version: int = 1
    width: int = Field(default=1664,ge=320,le=2560)
    height: int = Field(default=928,ge=320,le=2560)
    page_padding: int = Field(default=48,ge=16,le=80)
    gap: int = Field(default=32,ge=8,le=64)
    heading_size: int = Field(default=48,ge=28,le=64)
    body_size: int = Field(default=16,ge=14,le=20)
    background: str = Field(default='#ffffff',pattern=r'^#[0-9a-fA-F]{6}$')
    foreground: str = Field(default='#182522',pattern=r'^#[0-9a-fA-F]{6}$')
    accent: str = Field(default='#46ad48',pattern=r'^#[0-9a-fA-F]{6}$')
    hero_layout: Literal['single-column','two-columns'] = 'two-columns'
    hero_left_percent: int = Field(default=36,ge=30,le=60)
    stack_below: int = Field(default=900,ge=600,le=1000)
    sections: list[Section] = Field(default_factory=lambda:[Section(id='header',label='导航'),Section(id='hero',label='主内容'),Section(id='features',label='功能介绍',columns=4)],min_length=1,max_length=8)
    capture_state: str = '固定初始状态；分数0；动画尚未开始；没有登录态和随机内容'
    asset_policy: str = '仅简单内联SVG、CSS或Canvas图形，不使用Emoji、摄影、复杂插画和外部素材；不添加需求外的登录、排行榜或导航'


def normalize(value, viewport=None):
    spec=Spec.model_validate(value).model_dump()
    if len({s['id'] for s in spec['sections']}) != len(spec['sections']):
        raise ValueError('设计规格的模块ID不能重复')
    if viewport:spec.update(width=viewport['width'],height=viewport['height'])
    return spec


def stylesheet(spec):
    s=normalize(spec)
    cols=f"minmax(0,{s['hero_left_percent']}fr) minmax(0,{100-s['hero_left_percent']}fr)" if s['hero_layout']=='two-columns' else 'minmax(0,1fr)'
    rules=f'''*{{box-sizing:border-box}}:root{{--forge-bg:{s['background']};--forge-fg:{s['foreground']};--forge-accent:{s['accent']};--forge-gap:{s['gap']}px}}body{{margin:0!important;background:var(--forge-bg)!important;color:var(--forge-fg);font-family:Arial,"PingFang SC","Microsoft YaHei",sans-serif!important;font-size:{s['body_size']}px!important;line-height:1.6}}[data-forge-section]{{padding-left:{s['page_padding']}px!important;padding-right:{s['page_padding']}px!important}}[data-forge-section="hero"]{{display:grid!important;grid-template-columns:{cols}!important;gap:{s['gap']}px!important;align-items:center}}[data-forge-title]{{font-size:{s['heading_size']}px!important;line-height:1.15!important}}[data-forge-section]>*{{min-width:0}}'''
    for region in s['sections']:
        if region['columns']>1 and region['id']!='hero':
            rules+=f'''[data-forge-section="{region['id']}"]{{display:grid!important;grid-template-columns:repeat({region['columns']},minmax(0,1fr))!important;gap:{s['gap']}px!important}}'''
    rules+=f'''@media(max-width:{s['stack_below']}px){{[data-forge-section="hero"],[data-forge-section="features"]{{grid-template-columns:minmax(0,1fr)!important}}}}'''
    return rules


def constrain(html,spec):
    html=re.sub(r'<style\b[^>]*\bid=["\']forge-design-contract["\'][^>]*>[\s\S]*?</style>','',html,flags=re.I)
    style='<style id="forge-design-contract">'+stylesheet(spec)+'</style>'
    if re.search(r'</head\s*>',html,re.I):return re.sub(r'</head\s*>',lambda m:style+m[0],html,count=1,flags=re.I)
    return style+html


def repair_instructions(state):
    report=state.get('feedback',{})
    errors=report.get('errors',[])
    layout=report.get('layout',{})
    if errors or not layout.get('passed',True):focus='先修复运行错误和布局约束；只调整报告点名的模块和必要CSS'
    elif report.get('checks',{}).get('horizontal_overflow'):focus='只修复溢出与列宽，保持其他布局和业务逻辑'
    else:focus='按差异区域局部调整布局、字号、间距和颜色，禁止重新设计整页'
    return {'focus':focus,'preserve':['已通过的交互','现有功能与存储key','模块顺序和文案','确认的设计规格'],'evidence':report}
