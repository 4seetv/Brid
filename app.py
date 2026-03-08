import re
import time
import binascii
import aiohttp
from fastapi import FastAPI, Request
from Crypto.Cipher import AES

app = FastAPI()

USER_AGENT = "Mozilla/5.0"

cookie_cache = {}
cookie_time = {}

COOKIE_TTL = 1800


async def solve_challenge(url):

    async with aiohttp.ClientSession(headers={"User-Agent": USER_AGENT}) as session:

        async with session.get(url) as r:
            text = await r.text()

        if "slowAES" not in text:
            return {}

        a = binascii.unhexlify(re.search(r'a=toNumbers\("([a-f0-9]+)"\)', text).group(1))
        b = binascii.unhexlify(re.search(r'b=toNumbers\("([a-f0-9]+)"\)', text).group(1))
        c = binascii.unhexlify(re.search(r'c=toNumbers\("([a-f0-9]+)"\)', text).group(1))

        cipher = AES.new(a, AES.MODE_CBC, b)
        cookie = binascii.hexlify(cipher.decrypt(c)).decode().strip("0")

        return {"__test": cookie}


async def get_cookies(domain, url):

    now = time.time()

    if domain in cookie_cache and now - cookie_time[domain] < COOKIE_TTL:
        return cookie_cache[domain]

    cookies = await solve_challenge(url)

    cookie_cache[domain] = cookies
    cookie_time[domain] = now

    return cookies


@app.post("/relay/{token}/{php_url:path}")
async def relay(token: str, php_url: str, request: Request):

    update = await request.json()

    target = f"https://{php_url}"
    domain = php_url.split("/")[0]

    cookies = await get_cookies(domain, target)

    async with aiohttp.ClientSession(headers={"User-Agent": USER_AGENT}) as session:

        for attempt in range(2):

            try:

                async with session.post(target, json=update, cookies=cookies, timeout=8) as r:

                    try:

                        data = await r.json()

                        if "method" in data:

                            method = data.pop("method")

                            await session.post(
                                f"https://api.telegram.org/bot{token}/{method}",
                                json=data
                            )

                    except:
                        pass

                    break

            except:
                await asyncio.sleep(1)

    return {"ok": True}


@app.api_route("/bot{token}/{method}", methods=["GET","POST"])
async def tg_proxy(token: str, method: str, request: Request):

    url = f"https://api.telegram.org/bot{token}/{method}"

    async with aiohttp.ClientSession() as session:

        if request.method == "POST":

            data = await request.json()

            async with session.post(url, json=data) as r:
                return await r.json()

        else:

            async with session.get(url, params=request.query_params) as r:
                return await r.json()
