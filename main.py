import asyncio
import subprocess
from bilibili_api import video, parse_link, Credential, HEADERS, bangumi, login, user, sync, settings
from bilibili_api.login import login_with_password, login_with_sms, send_sms, PhoneNumber, Check
from bilibili_api.user import get_self_info
import aiohttp
import os
import json

asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
def init() -> Credential:
    # 初始化
    if not os.path.exists("config.json"):
        with open("config.json", "w") as config:
            json.dump({
                "login_mode": "QRcode",
                "SESSDATA": "",
                "BILI_JCT": "",
                "BUVID3": "",
                "username": "",
                "password": "",
                "phone_number": ""
            }, config)

    # 读取配置文件
    with open("config.json") as config:
        config = json.load(config)

    if config["login_mode"] == "Cookie":
        SESSDATA = config["SESSDATA"]
        BILI_JCT = config["BILI_JCT"]
        BUVID3 = config["BUVID3"]
        # 实例化 Credential 类
        credential = Credential(sessdata=SESSDATA, bili_jct=BILI_JCT, buvid3=BUVID3)

    elif config["login_mode"] == "QRcode":
        print("请登录：")
        credential = login.login_with_qrcode()
        try:
            credential.raise_for_no_bili_jct() # 判断是否成功
            credential.raise_for_no_sessdata() # 判断是否成功
        except:
            print("登录失败...")
            exit()

    elif config["login_mode"] == "Password":
        # 密码登录
        username = config["username"]
        password = config["password"]
        print("正在登录。")
        c = login_with_password(username, password)
        if isinstance(c, Check):
            # 还需验证
            phone = config["phone_number"]
            c.set_phone(PhoneNumber(phone, country="+86")) # 默认设置地区为中国大陆
            c.send_code()
            print("已发送验证码。")
            code = input("请输入验证码：")
            credential = c.login(code)
            print("登录成功！")
        else:
            credential = c
    elif config["login_mode"] == "PhoneNumber":
        # 验证码登录
        phone = config["phone_number"]
        print("正在登录。")
        send_sms(PhoneNumber(phone, country="+86")) # 默认设置地区为中国大陆
        code = input("请输入验证码：")
        credential = login_with_sms(PhoneNumber(phone, country="+86"), code)
        print("登录成功")

    # 检查 Cookie 是否有效
    if credential.check_valid(credential):
        print(f"欢迎，{sync(get_self_info(credential))['name']}!")
        cookies = credential.get_cookies()

        config["SESSDATA"] = cookies["SESSDATA"]
        config["BUVID3"] = cookies["buvid3"]
        config["BILI_JCT"] = cookies["bili_jct"]

        with open("config.json", "w") as f:
            json.dump(config, f)

        return credential
    else:
        print("Credential 无效 !")
        exit()


# 实例化 Credential 类
# credential = Credential(sessdata=SESSDATA, bili_jct=BILI_JCT, buvid3=BUVID3)
# FFMPEG 路径
FFMPEG_PATH = "ffmpeg\\bin\\ffmpeg.exe"

async def get_video(bvid, bangumi: bangumi.Bangumi):
    # 继承 banguim
    bangumi_info = bangumi.get_raw()
    if bangumi_info[0]["message"] == "success":
        bangumi_info = bangumi_info[0]["result"]

    # 实例化 Video 类
    v = video.Video(bvid=bvid, credential=credential)

    # 获取信息
    video_info = await v.get_info()
    pages = await v.get_pages()
    url = await v.get_download_url(0)

    # 视频轨链接
    video_url = ()
    for video_P in url['dash']['video']:
        if video_P['width'] == 1920 and video_P['height'] == 1080:
            if video_url == ():
                video_url = video_P['baseUrl'], video_P['bandwidth']
            elif video_P['bandwidth'] > video_url[1]:
                video_url = video_P['baseUrl'], video_P['bandwidth']
    if video_url == (): # 如果没有 1080P
        video_url = url["dash"]["video"][0]['baseUrl']
    else:
        video_url = video_url[0]
    
    # 音频轨链接
    audio_url = ()
    for audio_P in url['dash']['audio']:
        # if video_P['width'] == 1920 and video_P['height'] == 1080:
        if len(audio_url) == 0:
            audio_url = audio_P['baseUrl'], audio_P['bandwidth']
        elif audio_P['bandwidth'] > audio_url[1]:
            audio_url = audio_P['baseUrl'], audio_P['bandwidth']
    if len(audio_url) == 0: # 如果没有 1080P
        audio_url = url["dash"]["audio"][0]['baseUrl']
    else:
        audio_url = audio_url[0]
    audio_url = url["dash"]["audio"][0]['baseUrl']
    
    banguim_title = bangumi_info["title"]
    # 查找分P标题
    for ep in bangumi_info["episodes"]:
        if ep["bvid"] == bvid:
            ep_title = ep["share_copy"]
            No = ep["title"]
            break

    async with aiohttp.ClientSession() as sess:
        if not os.path.exists(os.path.join("cache", banguim_title)):
            os.makedirs(os.path.join("cache", banguim_title))
        save_path = os.path.join("cache", banguim_title)
        final_video_save_path = os.path.join(save_path, f"{No}_{bvid}.mp4")

        video_save_path = os.path.join(save_path, f"{No}_{bvid}_video_temp.m4s")
        # 下载视频流
        async with sess.get(video_url, headers=HEADERS) as resp:
            length = resp.headers.get('content-length')
            with open(os.path.join(save_path, f'{No}_{bvid}_video_temp.m4s'), 'wb') as f:
                process = 0
                async for chunk in resp.content.iter_chunked(1024):
                    f.write(chunk)
                    process += len(chunk)
                    # print(f'下载视频流 {process} / {length}')

        # 下载音频流
        audio_save_path = os.path.join(save_path, f'{No}_{bvid}_audio_temp.m4s')
        async with sess.get(audio_url, headers=HEADERS) as resp:
            length = resp.headers.get('content-length')
            with open(os.path.join(save_path, f'{No}_{bvid}_audio_temp.m4s'), 'wb') as f:
                process = 0
                async for chunk in resp.content.iter_chunked(1024):
                    f.write(chunk)
                    process += len(chunk)
                    # print(f'下载音频流 {process} / {length}')
        
        # 混流
        # command = f'{FFMPEG_PATH} -i "{video_save_path}" -i "{audio_save_path}" -vcodec copy -acodec copy "{final_video_save_path}"'
        if os.path.exists(final_video_save_path):
            os.remove(final_video_save_path)
        with open(os.devnull, 'wb') as devnull:
            subprocess.run(args=[FFMPEG_PATH, "-i", video_save_path, "-i", audio_save_path, "-vcodec", "copy", "-acodec", "copy", final_video_save_path], stdout=devnull, stderr=devnull)

        # 删除临时文件
        os.remove(video_save_path)
        os.remove(audio_save_path)
        print(f'已下载：{final_video_save_path}')

async def get_bangumi(media_id: int = None, url: str = None):
    if media_id is None and url is None:
        raise ValueError("需要 Media_id 或 番剧链接 中的一个 !")
    elif media_id is None:
        media_id = (await parse_link(url))[0]._Bangumi__media_id
    b = bangumi.Bangumi(media_id=media_id, credential=credential)
    
    # 打印信息
    info = b.get_raw()
    if info[0]["message"] == "success":
        info = info[0]["result"]
    print(f"========{info['title']}========")
    print(f'Link：{info["link"]}')
    print(f'简介：{info["evaluate"]}', sep='\n')
    print("========剧集信息========")
    # ep 信息
    for ep in info['episodes']:
        print(f'{ep["title"]}. {ep["long_title"]} | URL: {ep["link"]} | {ep["bvid"]}')
    print("========================")

    # 准备下载目录
    if not os.path.exists(os.path.join("cache", info['title'])):
        os.makedirs(os.path.join("cache", info['title']))

    tasks = []
    # for ep in b.ep_list:
    #     tasks.append(get_video(bvid=ep["bvid"], bangumi=b))
    # await asyncio.gather(*tasks)
    while len(b.ep_list) != 0:
        tasks.append(asyncio.create_task(get_video(bvid=b.ep_list.pop(0)["bvid"], bangumi=b)))
        if len(tasks) == 5 or len(b.ep_list) == 0:
            await asyncio.gather(*tasks)
            tasks = []

async def param_medias(medias: list):
    tasks = []
    while len(medias) != 0:
        media_id = medias.pop(0)
        tasks.append(asyncio.create_task(get_bangumi(media_id=media_id)))
        if len(tasks) == 5 or len(medias) == 0:
            await asyncio.gather(*tasks)
            tasks = []

if __name__ == '__main__':
    credential = init()
    if not os.path.exists("cache"):
        os.makedirs("cache")
    while True:
        asyncio.run(param_medias(
            input("输入需要下载的番剧的 media_Id 或者番剧主页链接 Eg:28237119 | https://www.bilibili.com/bangumi/media/md28237119/ :").split()
            ))
