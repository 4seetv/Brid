import httpx
import re
import binascii
from fastapi import FastAPI, Request, Response
from Crypto.Cipher import AES
from typing import Dict

app = FastAPI()

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
cookie_cache: Dict[str, dict] = {}

async def solve_infinity_challenge_async(url: str):
    async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}, timeout=10.0, follow_redirects=True) as client:
        try:
            res = await client.get(url)
            if "slowAES" not in res.text:
                return {c.name: c.value for c in res.cookies.jar}
            
            a = binascii.unhexlify(re.search(r'a=toNumbers\("([a-f0-9]+)"\)', res.text).group(1))
            b = binascii.unhexlify(re.search(r'b=toNumbers\("([a-f0-9]+)"\)', res.text).group(1))
            c = binascii.unhexlify(re.search(r'c=toNumbers\("([a-f0-9]+)"\)', res.text).group(1))
            
            cipher = AES.new(a, AES.MODE_CBC, b)
            cookie_val = binascii.hexlify(cipher.decrypt(c)).decode('utf-8').strip('0')
            return {"__test": cookie_val}
        except:
            return None

@app.post("/relay/{bot_token}/{php_url:path}")
async def inbound_relay(bot_token: str, php_url: str, request: Request):
    target_url = f"https://{php_url}"
    domain = php_url.split('/')[0]
    tg_data = await request.json()

    cookies = cookie_cache.get(domain)
    if not cookies:
        cookies = await solve_infinity_challenge_async(target_url)
        if cookies: cookie_cache[domain] = cookies

    async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}, timeout=15.0) as client:
        try:
            await client.post(target_url, json=tg_data, cookies=cookies)
            return {"status": "forwarded"}
        except Exception as e:
            return {"error": str(e)}

@app.api_route("/bot{token}/{method}", methods=["GET", "POST"])
async def outbound_proxy(token: str, method: str, request: Request):
    url = f"https://api.telegram.org/bot{token}/{method}"
    params = dict(request.query_params)
    content = await request.body()
    
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.request(
            method=request.method,
            url=url,
            params=params,
            content=content,
            headers={"User-Agent": USER_AGENT}
        )
        return Response(content=resp.content, status_code=resp.status_code, media_type=resp.headers.get("content-type"))

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
