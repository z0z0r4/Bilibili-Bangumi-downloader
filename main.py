import asyncio
import subprocess
import aiohttp
import os
import json
from bilibili_api import parse_link, Credential, HEADERS, bangumi, login, user, sync
from bilibili_api.login import login_with_password, login_with_sms, send_sms, PhoneNumber, Check
from bilibili_api.user import get_self_info

# bilibili_api Docs: https://nemo2011.github.io/bilibili-api

asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy()) # TODO 防报错

async def init() -> Credential:
    # 初始化
    if not os.path.exists("config.json"):
        with open("config.json", "w") as config:
            json.dump({
                "FFmpeg_Path": "ffmpeg",
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
    
    # FFMPEG 路径
    FFMPEG_PATH = config["FFmpeg_Path"]
    with open(os.devnull, 'wb') as devnull:
        cmd = subprocess.run(args=[FFMPEG_PATH, "-version"], stdout=devnull, stderr=devnull)
        if cmd.returncode == 0:
            print(f"FFmpeg 路径：{FFMPEG_PATH} 可用")
        else:
            print("FFmpeg 路径错误 !请在config.json中修改FFmpeg_Path")
            os.system('pause')



    # TODO 感觉臃肿...
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
            os.system('pause')

    elif config["login_mode"] == "Password":
        # 密码登录
        if config["username"] == "" or config["password"] == "":
            print("请在config.json中填写用户名和密码")
            os.system('pause')

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
        if phone == "":
            print("请在config.json中填写手机号码")
            os.system('pause')

        print("正在登录。")
        send_sms(PhoneNumber(phone, country="+86")) # 默认设置地区为中国大陆
        code = input("请输入验证码：")
        credential = login_with_sms(PhoneNumber(phone, country="+86"), code)
        print("登录成功")

    # 检查 Cookie 是否有效
    if await credential.check_valid():
        print(f"欢迎，{(await get_self_info(credential))['name']}!")
        cookies = credential.get_cookies()

        # 自动存入 config.json
        config["SESSDATA"] = cookies["SESSDATA"]
        config["BUVID3"] = cookies["buvid3"]
        config["BILI_JCT"] = cookies["bili_jct"]

        with open("config.json", "w") as f:
            json.dump(config, f)
        
        user_info = await user.get_self_info(credential=credential)
        if user_info["vip"]["status"] == 0:
            print(f'请注意 {user_info["name"]} 不是大会员，可能受到B站限制')
        return credential, FFMPEG_PATH
    else:
        print("Credential 无效 !")
        os.system('pause')

async def get_video(epid, b: bangumi.Bangumi):
    # 继承 banguim
    bangumi_info = b.get_raw()
    if bangumi_info[0]["message"] == "success":
        bangumi_info = bangumi_info[0]["result"]

    # 实例化 Episode 类
    e = bangumi.Episode(epid=epid, credential=credential)

    # 获取信息
    # ep_info = await e.get_episode_info()
    # pages = await e.get_pages()
    url = await e.get_download_url()

    # TODO 更好的分辨率选择
    if url["type"] == "DASH":
        # 视频轨链接
        video_url = ()
        for video_P in url['dash']['video']:
            if video_P['width'] == 1920 and video_P['height'] == 1080:
                if video_url == ():
                    video_url = video_P['baseUrl'], video_P['size']
                elif video_P['size'] > video_url[1]:
                    video_url = video_P['baseUrl'], video_P['size']
        if video_url == (): # 如果没有 1080P
            video_url = url["dash"]["video"][0]['baseUrl']
        else:
            video_url = video_url[0]
        
        # 音频轨链接
        audio_url = ()
        for audio_P in url['dash']['audio']:
            # if video_P['width'] == 1920 and video_P['height'] == 1080:
            if len(audio_url) == 0:
                audio_url = audio_P['baseUrl'], audio_P['size']
            elif audio_P['size'] > audio_url[1]:
                audio_url = audio_P['baseUrl'], audio_P['size']
        if len(audio_url) == 0: # 如果没有 1080P
            audio_url = url["dash"]["audio"][0]['baseUrl']
        else:
            audio_url = audio_url[0]
        audio_url = url["dash"]["audio"][0]['baseUrl']
        is_flv = False
    
    else: # 可能为FLV
        video_size = 0
        for durl in url["durl"]:
            n_video_size = durl["size"]
            if n_video_size > video_size:
                video_url = durl["url"]
                video_size = n_video_size
        is_flv = True

    banguim_title = bangumi_info["title"]
    # 查找分P标题
    for ep in bangumi_info["episodes"]:
        if ep["id"] == epid:
            # ep_title = ep["share_copy"]
            ep_title = ep["title"]
            break
    
    if not os.path.exists(os.path.join("cache", banguim_title)):
        os.makedirs(os.path.join("cache", banguim_title))
    save_path = os.path.join("cache", banguim_title)
    final_video_save_path = os.path.join(save_path, f"{ep_title}_{epid}.mp4")

    if os.path.exists(final_video_save_path):
        print(f"已存在：{final_video_save_path}") # TODO 需要检查视频文件是否完整
        await asyncio.sleep(1) # 防止被B站封IP
        return 0

    if is_flv:
        video_save_path = os.path.join(save_path, f"{ep_title}_{epid}_video_temp.flv")

    # TODO 赶工，try部分需要优化
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(600)) as sess:
        try:
            # 下载视频流
            video_save_path = os.path.join(save_path, f"{ep_title}_{epid}_video_temp.m4s")
            async with sess.get(video_url, headers=HEADERS) as resp:
                length = resp.headers.get('content-length')
                with open(os.path.join(save_path, f'{ep_title}_{epid}_video_temp.m4s'), 'wb') as f:
                    process = 0
                    async for chunk in resp.content.iter_chunked(1024):
                        f.write(chunk)
                        process += len(chunk)
            print(f'下载视频流 {ep_title}_{epid}_video_temp.m4s 完成')
        except asyncio.exceptions.TimeoutError:
            print(f'下载视频流 {ep_title}_{epid}_video_temp.m4s {video_url} 超时')
            os.system('pause')
        except Exception as e:
            print(f"下载 {video_url} 错误")

        if is_flv == False:
            # 下载音频流
            audio_save_path = os.path.join(save_path, f'{ep_title}_{epid}_audio_temp.m4s')
            try:
                async with sess.get(audio_url, headers=HEADERS) as resp:
                    length = resp.headers.get('content-length')
                    with open(os.path.join(save_path, f'{ep_title}_{epid}_audio_temp.m4s'), 'wb') as f:
                        process = 0
                        async for chunk in resp.content.iter_chunked(1024):
                            f.write(chunk)
                            process += len(chunk)
                print(f'下载音频流 {ep_title}_{epid}_audio_temp.m4s 完成')
            except asyncio.exceptions.TimeoutError:
                print(f'下载视频流 {ep_title}_{epid}_video_temp.m4s {video_url} 超时')
                os.system('pause')
            except Exception as e:
                print(f"下载 {audio_url} 错误")
    
    # TODO 赶工，需要优化
    if is_flv:
        with open(os.devnull, 'wb') as devnull:
            subprocess.run(args=[FFMPEG_PATH, "-i", video_save_path, "-c", "copy", final_video_save_path], stdout=devnull, stderr=devnull)
        # 删除临时文件
        os.remove(video_save_path)
        
    else:
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
    # TODO 已经不记得此处是否可以使用番剧 URL...
    if media_id is None and url is None:
        raise ValueError("需要 Media_id 或 番剧链接 中的一个 !")
    elif media_id is None:
        media_id = (await parse_link(url))[0].get_media_id()
    b = bangumi.Bangumi(media_id=media_id, credential=credential)
    
    # TODO | 修缮打印信息格式 Future https://nemo2011.github.io/bilibili-api/#/modules/bangumi?id=def-get_episode_info
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
    ep_list = (await b.get_episode_list())['main_section']["episodes"]
    while len(ep_list) != 0:
        tasks.append(asyncio.create_task(get_video(epid=ep_list.pop(0)["id"], b=b)))
        if len(tasks) == 3 or len(ep_list) == 0:
            await asyncio.gather(*tasks)
            tasks = []

async def param_medias(medias: list):
    tasks = [] # TODO 需要修改并行下载...
    while len(medias) != 0:
        media_id = medias.pop(0)
        tasks.append(asyncio.create_task(get_bangumi(media_id=media_id)))
        if len(tasks) == 3 or len(medias) == 0: # 限制并发数
            await asyncio.gather(*tasks)
            tasks = []

if __name__ == '__main__':
    credential, FFMPEG_PATH = asyncio.run(init())
    if not os.path.exists("cache"):
        os.makedirs("cache")
    while True:
        asyncio.run(param_medias(
            input("输入需要下载的番剧的 media_Id 或者番剧主页链接 Eg:28237119 | https://www.bilibili.com/bangumi/media/md28237119/ :").split()
            ))