import json, sys, os

board_path = 'D:/AISleepGen_Optimized/expert_board.json'
board = json.load(open(board_path, 'r', encoding='utf-8'))
iv = board.get('auto_intervention', {})
if iv.get('has_intervention'):
    sys.path.insert(0, 'D:/AISleepGen_Optimized')
    from intervene_injector import get_descriptive_text
    t = get_descriptive_text()
    if t:
        print('干预建议就绪:')
        print(t)
        del board['auto_intervention']
        json.dump(board, open(board_path, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
        print('[已清除干预标志]')
    else:
        print('(无干预文本)')
else:
    print('(无待执行干预)')
