"""Render a documentation SVG from the actual Flex Message example JSON."""
from html import escape
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    examples = {name: json.loads((ROOT / 'examples' / f'{name}-flex.json').read_text(encoding='utf-8'))
                for name in ('menu', 'unpaid', 'paid')}
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="660" viewBox="0 0 1200 660" role="img" aria-labelledby="title desc">',
             '<title id="title">LINE 訂單助手 Flex Message 卡片結構預覽</title>',
             '<desc id="desc">由專案範例 JSON 產生的操作選單、未入帳及已付款卡片結構示意。非 LINE 實機截圖。</desc>',
             '<style>text{font-family:system-ui,"Microsoft JhengHei","Noto Sans TC",sans-serif}</style>',
             '<rect width="1200" height="660" rx="24" fill="#edf3ef"/>']

    def rect(x, y, width, height, color, radius=12):
        parts.append(f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="{radius}" fill="{color}"/>')

    def text(x, y, value, size=16, color='#243b2d', weight=400, anchor='start'):
        parts.append(f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" font-weight="{weight}" text-anchor="{anchor}">{escape(str(value))}</text>')

    def button(x, y, label, green=False, width=300):
        rect(x, y, width, 43, '#06c755' if green else '#edf2ef', 9)
        text(x + width / 2, y + 27, label, 14, '#ffffff' if green else '#365340', 600, 'middle')

    text(34, 43, 'LINE Order & Payment Bot', 24, '#163c28', 700)
    text(34, 71, '原生 Flex Message 結構預覽 · 範例資料 · 非 LINE 實機截圖', 14, '#678171')
    for x, label in [(34, '01 / 操作選單'), (424, '02 / 未入帳'), (814, '03 / 已付款')]:
        text(x, 112, label, 14, '#658471', 600)
        rect(x, 130, 352, 480, '#ffffff', 16)

    menu = examples['menu']['contents']['body']['contents']
    x = 60
    text(x, 179, menu[0]['text'], 24, '#173d2a', 700)
    text(x, 214, menu[1]['text'], 15, '#06a66b', 600)
    text(x, 257, '選擇通道後輸入 +300，即可建立訂單。', 13, '#69776e')
    text(x, 281, '也可以輸入其他整數金額，例如 +500。', 13, '#69776e')
    for index, item in enumerate(menu[3]['contents']):
        button(x + index * 104, 317, item['action']['label'], index == 0, 92)
    button(x, 383, menu[4]['action']['label'], True)
    button(x, 439, menu[5]['action']['label'])
    text(x + 150, 562, menu[6]['text'], 12, '#87918e', 400, 'middle')

    for name, left in [('unpaid', 424), ('paid', 814)]:
        bubble = examples[name]['contents']
        body = bubble['body']['contents']
        x = left + 26
        rect(left, 130, 352, 88, '#f0faf4', 16)
        rect(left, 190, 352, 28, '#f0faf4', 0)
        text(x, 159, bubble['header']['contents'][0]['text'], 12, '#54816a')
        text(x, 195, bubble['header']['contents'][1]['text'], 24, '#173d2a', 700)
        text(x, 258, body[0]['contents'][0]['text'], 30, '#172a20', 700)
        text(left + 326, 255, body[0]['contents'][1]['text'], 15,
             body[0]['contents'][1]['color'], 700, 'end')
        parts.append(f'<path d="M{x} 280h300" stroke="#e4ece6"/>')
        for index, row in enumerate(body[2:4]):
            text(x, 309 + index * 28, row['contents'][0]['text'], 12, '#7c8795')
            text(x + 83, 309 + index * 28, row['contents'][1]['text'], 13, '#253044')
        rect(x, 356, 300, 76, '#f5f7f9', 10)
        text(x + 16, 382, body[4]['contents'][0]['text'], 12, '#7c8795')
        text(x + 16, 414, body[4]['contents'][1]['text'], 25, '#253044', 700)
        row = body[5]['contents']
        text(x, 456, row[0]['text'], 12, '#7c8795')
        text(x + 83, 456, row[1]['text'], 13, '#253044')
        for index, component in enumerate(bubble['footer']['contents']):
            if component['type'] == 'button':
                button(x, 477 + index * 51, component['action']['label'], component['style'] == 'primary')
        text(x + 150, 594, '作品集模擬流程，代碼不可實際繳費。', 11, '#87918e', 400, 'middle')

    text(34, 641, 'Flask · SQLite · LINE Messaging API · Mock Payment Service', 13, '#69816f')
    parts.append('</svg>')
    target = ROOT / 'docs' / 'assets' / 'flex-preview.svg'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('\n'.join(parts) + '\n', encoding='utf-8')
    print('Flex preview generated: docs/assets/flex-preview.svg')


if __name__ == '__main__':
    main()
