#!/usr/bin/env python
import zipfile, xml.etree.ElementTree as ET, os

docx_dir = r'E:\笔记本D盘备份\发烧友快乐音乐湖\输出给柔灵'
output_dir = r'D:\AISleepGen_Optimized\static\rouling_scripts'
os.makedirs(output_dir, exist_ok=True)

wav_to_docx = {}
wavs = [f.replace('.WAV','') for f in os.listdir(docx_dir) if f.endswith('.WAV')]

print(f"Extracting docx text for {len(wavs)} WAV files...")

for f in sorted(os.listdir(docx_dir)):
    if not f.endswith('.docx'):
        continue
    
    fp = os.path.join(docx_dir, f)
    name = f.replace('.docx','')
    
    try:
        with zipfile.ZipFile(fp) as z:
            xml_content = z.read('word/document.xml')
            root = ET.fromstring(xml_content)
            ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
            text_parts = []
            for t in root.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t'):
                if t.text:
                    text_parts.append(t.text)
            full_text = ''.join(text_parts)
    except Exception as e:
        print(f"  ERROR reading {f}: {e}")
        continue
    
    # 找匹配的WAV
    matched_wav = None
    for w in wavs:
        if w[:4] in name or name[:4] in w:
            matched_wav = w
            break
    
    out_name = f"{matched_wav or name}.txt"
    out_path = os.path.join(output_dir, out_name)
    with open(out_path, 'w', encoding='utf-8') as outf:
        outf.write(full_text)
    
    status = f"→ {matched_wav}.WAV" if matched_wav else "(no WAV match)"
    print(f"  {f} ({len(full_text)}字) {status}")
    print(f"    saved: {out_name}")
    print(f"    first 60字: {full_text[:60]}...")

print(f"\nAll saved to {output_dir}")
