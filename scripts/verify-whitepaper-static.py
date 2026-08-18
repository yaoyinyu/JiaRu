# -*- coding: utf-8 -*-
"""静态验证 v2：MD 标题与 HTML 标题一致性。"""
import re, sys
sys.stdout.reconfigure(encoding='utf-8')

md = open(r'E:\AI Project\Codex\JiaRu\docs\technical-whitepaper.md', encoding='utf-8').read()
html = open(r'C:\Users\YaoYinyu\Downloads\JiaRu_whitepaper_v1.1.467_updated.html', encoding='utf-8').read()

md_h2 = re.findall(r'^## (.+)$', md, re.M)
md_h3 = re.findall(r'^### (.+)$', md, re.M)
# 代码块内的 ### 模块名称（MD 1287-1303 为 ```md 代码块）不算真实 h3
md_h3 = [h for h in md_h3 if h != '模块名称']

html_h2 = re.findall(r'<h2 data-chapter="\d+"[^>]*>(.*?)</h2>', html, re.S)
html_h3 = re.findall(r'<h3 data-level="3"[^>]*>(.*?)</h3>', html, re.S)

def strip_tag(s):
    s = re.sub(r'<a[^>]*>#</a>', '', s)      # 去掉锚点
    s = re.sub(r'<[^>]+>', '', s)            # 去掉所有标签
    return re.sub(r'\s+', '', s)

def norm(s):
    return re.sub(r'\s+', '', s).replace('`', '')

print('MD h2:', len(md_h2), 'HTML h2:', len(html_h2))
print('MD h3:', len(md_h3), 'HTML h3:', len(html_h3))

mismatch = []
for m, h in zip(md_h2, html_h2):
    mm = norm(m)
    hm = strip_tag(h)
    # h2 显示标题去掉了 "N. " 前缀
    mm_display = re.sub(r'^\d+\.\s*', '', mm)
    if mm_display not in hm and hm not in mm_display:
        mismatch.append(('h2', m, hm))
for m, h in zip(md_h3, html_h3):
    mm = norm(m)
    hm = strip_tag(h)
    if mm not in hm and hm not in mm:
        mismatch.append(('h3', m, hm))
print('标题不匹配:', len(mismatch))
for x in mismatch:
    print(x)
