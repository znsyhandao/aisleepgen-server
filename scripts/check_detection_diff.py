import pandas as pd, sys; sys.stdout.reconfigure(encoding='utf-8')

old = pd.read_csv('D:/AISleepGen_Optimized/sleep-skin features/facial_features_v9_backup_20260510.csv')
new = pd.read_csv('D:/AISleepGen_Optimized/sleep-skin features/facial_features_v9.csv')

old['d'] = old['face_detected'].astype(str).str.lower().str.strip()
new['d'] = new['face_detected'].astype(str).str.lower().str.strip()

merged = pd.merge(old[['file','d']], new[['file','d']], on='file', suffixes=('_old','_new'))

print(f'旧版检测True新版True: {((merged.d_old=="true") & (merged.d_new=="true")).sum()}')
print(f'旧版True新版非True: {((merged.d_old=="true") & (merged.d_new!="true")).sum()}')
print(f'旧版非True新版True: {((merged.d_old!="true") & (merged.d_new=="true")).sum()}')
print(f'两者都非True: {((merged.d_old!="true") & (merged.d_new!="true")).sum()}')
print(f'总数: {len(merged)}')

lost = merged[(merged.d_old=="true") & (merged.d_new!="true")]
if len(lost) > 0:
    print(f'\n丢失的 {len(lost)} 个文件:')
    for _, r in lost.head(30).iterrows():
        print(f'  {r["file"]}')
