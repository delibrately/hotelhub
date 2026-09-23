"""Public retreat pages. Editorial content is independent of reservation records."""
from django.http import Http404
from django.shortcuts import render

IMAGE_ROOT = 'retreat/images/'
ROOMS = [
    dict(slug='forest', name='林间宿', english='THE FOREST CABIN', number='01',
         subtitle='把一整片森林，留在窗前。',
         description='树影落在玻璃屋顶，白帘轻轻垂落。坐在露台上，让山林的光与风，陪你度过一个不用赶路的下午。',
         cover='forest-cabin.jpg', images=['forest-cabin.jpg', 'forest-interior.jpg', 'terrace.jpg'],
         tags=['含双人早餐', '独立卫浴', '林间露台'], bed='1.8 × 2 米大床', guests='2 位成人，可携 1 位儿童', breakfast='含双人早餐', bathroom='室内独立卫浴', checkin='13:00 入住 · 次日 11:00 退房',
         facilities=['室外浴缸', '空调', '冰箱', '投影仪', '电动窗帘', 'Wi-Fi', '露台网床']),
    dict(slug='hillside', name='半山度假屋', english='THE HILLSIDE RETREAT', number='02',
         subtitle='在半山，把日子过得轻一点。',
         description='推开房门，是木质露台和满眼的绿。给自己留一段空白时间，在山风里坐一会儿，也在这里好好睡一觉。',
         cover='hillside-terrace.jpg', images=['hillside-terrace.jpg'],
         tags=['含双人早餐', '独立卫浴', '室外浴缸'], bed='1.8 × 2 米大床', guests='2 位成人，可携 1 位儿童', breakfast='含双人早餐', bathroom='室内独立卫浴', checkin='13:00 入住 · 次日 11:00 退房',
         facilities=['室外浴缸', '空调', '冰箱', '投影仪', '电动窗帘', 'Wi-Fi']),
    dict(slug='sunshine', name='阳光房', english='THE SUNLIT CABIN', number='03',
         subtitle='一间小屋，一段明亮的假期。',
         description='小屋藏在绿意旁，屋前有坐下来的地方。白天走进自然，傍晚回到自己的房间，享受简单、自在的度假时光。',
         cover='sunshine-cabin.jpg', images=['sunshine-cabin.jpg'],
         tags=['1.8 米大床', '独立卫浴', '不含早餐'], bed='1.8 米大床', guests='具体入住人数请咨询', breakfast='不含早餐', bathroom='室内独立卫浴', checkin='12:00 入住 · 次日 10:00 退房',
         facilities=['空调', 'Wi-Fi', '屋前休憩空间']),
    dict(slug='tent', name='轻奢帐篷', english='THE MEADOW TENT', number='04',
         subtitle='住进草地，离夜色近一点。',
         description='白色帐篷散落在草地上。天幕下喝茶、聊天，等山谷的灯一盏盏亮起，把平常的夜晚过成另一种模样。',
         cover='meadow-tents.jpg', images=['meadow-tents.jpg', 'tents-evening.jpg'],
         tags=['大床 / 双床', '公共卫浴', '不含早餐'], bed='大床 1.7 × 2 米 / 双床各 1 × 2 米', guests='2 位成人', breakfast='不含早餐', bathroom='公共卫生间及淋浴间', checkin='13:00 入住 · 次日 11:00 退房',
         facilities=['床品', '电热毯', '电源', '热水壶', '茶具', '休闲桌椅', 'Wi-Fi']),
]


def retreat_home(request):
    return render(request, 'retreat/home.html', {'rooms': ROOMS})


def retreat_room(request, slug):
    room = next((item for item in ROOMS if item['slug'] == slug), None)
    if room is None:
        raise Http404('房型不存在')
    return render(request, 'retreat/room.html', {'room': room, 'other_rooms': [r for r in ROOMS if r['slug'] != slug]})
