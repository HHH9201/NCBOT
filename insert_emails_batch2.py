#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
插入第二批邮箱数据到 Turso 数据库
"""
import aiohttp
import asyncio

# Turso 数据库配置
TURSO_URL = "https://trae-email-hhh9201.aws-ap-northeast-1.turso.io"
TURSO_TOKEN = "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3NzUwMjkzMjAsImlkIjoiMDE5ZDQ3ZmQtYmMwMS03NTNiLTgwZWMtOTU2YjgxOGM4MDI5IiwicmlkIjoiMzYwOGM2YWMtNmY5Ny00NjczLWJiYzItODA1NDE0NjUwY2NmIn0.XbP7MPJw3pAi9s6Eu1QOerclRgFK_0WOBm5rI5eq6X2fCuw7u71Czin6vFC0HfEDav8wKvTMlyHcoU-P_Ob7CQ"

# 第二批邮箱数据
emails_data = [
    ("fl46sbdy@tempmail.cn", "jdpJ2udI!qcK"),
    ("upo1r9mc@tempmail.cn", "0sCSNd^Hg3Kb"),
    ("hx44dzxn@tempmail.cn", "9vr&eJHr&HRt"),
    ("6lby2sob@tempmail.cn", "LaZWL^u829*D"),
    ("y5vfj3cf@tempmail.cn", "ujQ#ft%BhKkh"),
    ("csqr2wk4@tempmail.cn", "G^UbuWxbRVIa"),
    ("0tr9y4dv@tempmail.cn", "e!zXlMG*^ENb"),
    ("d1ypgic4@tempmail.cn", "&BRhjMOOlMtc"),
    ("tr4cygmx@tempmail.cn", "#qFhJhL6M8%r"),
    ("s5jbehwf@tempmail.cn", "z^g9X%0pAHGN"),
    ("hinkpqj5@tempmail.cn", "d^iSCmunbDsk"),
    ("t0i46m8k@tempmail.cn", "ZtrttD%t@Xa6"),
    ("cbetx2ou@tempmail.cn", "8BgPWa1@^H*h"),
    ("rr98mul7@tempmail.cn", "r4rrGh7Vr7xd"),
    ("ae7qmgjl@tempmail.cn", "qc4*%eMQfp&M"),
    ("x9rp4ff3@tempmail.cn", "sYM4C*!q0EM$"),
    ("bpc4zf7q@tempmail.cn", "Uq&ufaz1Uqd!"),
    ("ngectjas@tempmail.cn", "!%09e$owG!G6"),
    ("tzr2rhha@tempmail.cn", "MFs535lJMrpK"),
    ("9ivqb40b@tempmail.cn", "R0Zx#NxqGY^h"),
    ("459k5vp2@tempmail.cn", "4WIrzEt0scP%"),
    ("948rstss@tempmail.cn", "&&vm7KP#FHfV"),
    ("bmvim7d3@tempmail.cn", "g7jbovSkSwH9"),
    ("ch92ybar@tempmail.cn", "o7s^%^QxqK9o"),
    ("vl4fhfqj@tempmail.cn", "*Zyhyp9#4Bd3"),
    ("0802uong@tempmail.cn", "bcnptbC%v!pZ"),
    ("c2qp85ku@tempmail.cn", "yOUR8PLJFwG3"),
    ("dnj9c489@tempmail.cn", "wcQ8Pj8dZT11"),
    ("y3buw49x@tempmail.cn", "koPbcRJuJse0"),
    ("k3czij35@tempmail.cn", "$ijb%SYwG!86"),
    ("17kc2sb7@tempmail.cn", "SojN7@vnsAoY"),
    ("xdxy6mpd@tempmail.cn", "yE^S72mc^Xri"),
    ("i521kphm@tempmail.cn", "1AKfZZBOjTJ%"),
    ("8cet56k4@tempmail.cn", "tt*5cIXbVk8O"),
    ("z8sck74h@tempmail.cn", "7mklSHrH$M84"),
    ("g9c65a6j@tempmail.cn", "uT2V$58@Ow4b"),
    ("1242cor6@tempmail.cn", "GrG%@v%Z1##w"),
    ("vdtybyd5@tempmail.cn", "p9V$i0i1%ZI9"),
    ("opcj3htj@tempmail.cn", "T^wn3tRSKwip"),
    ("r6wpik89@tempmail.cn", "A!XNkYr^rXYU"),
    ("j4j8nz7m@tempmail.cn", "yt@oBo^hh5eb"),
    ("opn7zj9q@tempmail.cn", "fo^5CH!#tRJC"),
    ("07e9g30i@tempmail.cn", "sAFFC4!3W6LH"),
    ("tsuiw06m@tempmail.cn", "MrkJ9Dh9K5ld"),
    ("redcowbt@tempmail.cn", "i$2bZi8EAmKz"),
    ("5lgnq8a9@tempmail.cn", "uWYAfBjQ3!MW"),
    ("0iq9bqks@tempmail.cn", "Jte*Ha8zN1gf"),
    ("75q23jv6@tempmail.cn", "2yFLmiMawdmb"),
    ("wrelziz6@tempmail.cn", "@P^qwA5FVyRR"),
    ("21qkgkdt@tempmail.cn", "m3DtB%6ppi6c"),
    ("1mq0sxhx@tempmail.cn", "Gt#ImV6jLAcC"),
    ("z4xeay51@tempmail.cn", "tUjYXqpg^0mG"),
    ("qszdm2b0@tempmail.cn", "@z!!eSBBTxEq"),
    ("f6ruu5w5@tempmail.cn", "t3Zy7GarDo3!"),
    ("2bbbrhye@tempmail.cn", "uo!Kd*vYU7TD"),
    ("egnwl3hp@tempmail.cn", "GcaCHvXLfZNe"),
    ("l7spm5en@tempmail.cn", "P6HLJ55JcfZD"),
    ("tpl1zbf6@tempmail.cn", "FpdKuz9s3OlA"),
    ("4a59zgjh@tempmail.cn", "fpTFcINlf*9v"),
    ("nj2yn0y4@tempmail.cn", "$9@c$JMx8AQD"),
    ("fg80nwr0@tempmail.cn", "^!MuR4s@dNFh"),
    ("vhn7nncv@tempmail.cn", "O6NeV!iwhS5f"),
]


async def execute_sql(session: aiohttp.ClientSession, sql: str, args: list = None):
    """执行 SQL 语句 (Turso HTTP API)"""
    if args is None:
        args = []

    headers = {
        "Authorization": f"Bearer {TURSO_TOKEN}",
        "Content-Type": "application/json"
    }

    params = []
    for arg in args:
        if isinstance(arg, bool):
            params.append({"type": "integer", "value": str(int(arg))})
        elif isinstance(arg, int):
            params.append({"type": "integer", "value": str(arg)})
        elif isinstance(arg, str):
            params.append({"type": "text", "value": arg})
        else:
            params.append({"type": "text", "value": str(arg)})

    payload = {
        "requests": [
            {
                "type": "execute",
                "stmt": {
                    "sql": sql,
                    "args": params
                }
            }
        ]
    }

    async with session.post(
        f"{TURSO_URL}/v2/pipeline",
        headers=headers,
        json=payload
    ) as response:
        if response.status != 200:
            text = await response.text()
            raise Exception(f"Turso API error: {response.status} - {text}")

        data = await response.json()

        if "results" in data and len(data["results"]) > 0:
            result = data["results"][0]
            if "error" in result:
                raise Exception(f"SQL error: {result['error']}")
            return result
        return {}


async def insert_email(session: aiohttp.ClientSession, email: str, key: str):
    """插入单个邮箱"""
    try:
        await execute_sql(session, """
            INSERT INTO email_accounts (email, key, is_assigned) 
            VALUES (?, ?, 0)
            ON CONFLICT(email) DO UPDATE SET
                key = excluded.key,
                is_assigned = 0,
                assigned_to = NULL,
                assigned_at = NULL
        """, [email, key])
        return True
    except Exception as e:
        print(f"[ERROR] 插入失败 {email}: {e}")
        return False


async def main():
    async with aiohttp.ClientSession() as session:
        # 插入所有邮箱
        success_count = 0
        fail_count = 0

        for i, (email, password) in enumerate(emails_data, 1):
            if await insert_email(session, email, password):
                success_count += 1
                print(f"[{i}/{len(emails_data)}] ✓ {email}")
            else:
                fail_count += 1
                print(f"[{i}/{len(emails_data)}] ✗ {email}")

        print(f"\n{'='*50}")
        print(f"插入完成！")
        print(f"成功: {success_count}")
        print(f"失败: {fail_count}")
        print(f"总计: {len(emails_data)}")


if __name__ == "__main__":
    asyncio.run(main())
