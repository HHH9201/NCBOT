#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
插入邮箱数据到 Turso 数据库
"""
import aiohttp
import asyncio

# Turso 数据库配置
TURSO_URL = "https://trae-email-hhh9201.aws-ap-northeast-1.turso.io"
TURSO_TOKEN = "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3NzUwMjkzMjAsImlkIjoiMDE5ZDQ3ZmQtYmMwMS03NTNiLTgwZWMtOTU2YjgxOGM4MDI5IiwicmlkIjoiMzYwOGM2YWMtNmY5Ny00NjczLWJiYzItODA1NDE0NjUwY2NmIn0.XbP7MPJw3pAi9s6Eu1QOerclRgFK_0WOBm5rI5eq6X2fCuw7u71Czin6vFC0HfEDav8wKvTMlyHcoU-P_Ob7CQ"

# 邮箱数据
emails_data = [
    ("5zkscqfw@tempmail.cn", "%MCwU!8tKsED"),
    ("7pb6aeyw@tempmail.cn", "$diutuso68KS"),
    ("0t23myxq@tempmail.cn", "NnJlNACXWj%7"),
    ("wkvh8pfw@tempmail.cn", "qsF!mRqyRils"),
    ("2iqzvje8@tempmail.cn", "svV&FJAqB!&f"),
    ("j7drgsqe@tempmail.cn", "AZVN%qoWW1Im"),
    ("5prnk1q4@tempmail.cn", "mmhBjWK^ItF7"),
    ("lnm0mh25@tempmail.cn", "q&0mDPhyOA@0"),
    ("sob3me66@tempmail.cn", "&aBxSA4j&w8N"),
    ("a3umk6g9@tempmail.cn", "h#i5#yO&px4b"),
    ("3vey9a13@tempmail.cn", "&aGkvWeQhPrc"),
    ("h7fxz8nu@tempmail.cn", "sLA8yjNuBleh"),
    ("cfgg4ksq@tempmail.cn", "juOIGKWNuCHJ"),
    ("hb4t7yp7@tempmail.cn", "x2uYkrIerH0R"),
    ("ldlgu1rf@tempmail.cn", "r3^Y2Wf!hfzA"),
    ("xuo03too@tempmail.cn", "A6ZunYFu9QWF"),
    ("dt6mdos0@tempmail.cn", "g0*%QE!b^AAu"),
    ("kp8nsxo1@tempmail.cn", "B7wa28wpCbES"),
    ("m8ozr655@tempmail.cn", "uW!31QRGY9k9"),
    ("qjz8xyxr@tempmail.cn", "kY4g6xtByPHw"),
    ("xwhj08zd@tempmail.cn", "NL75$QppXmsA"),
    ("c1edmbf8@tempmail.cn", "t8waF2DKgr&h"),
    ("19jxvdj3@tempmail.cn", "&9LPkvU&WFc9"),
    ("r832xlc7@tempmail.cn", "ca!XzNV&AFti"),
    ("wl1gqz6z@tempmail.cn", "S9I41ypNxzgh"),
    ("92a5jyno@tempmail.cn", "BgnifIZfDe3Z"),
    ("r53sdm95@tempmail.cn", "ZxfNoEgVCr@p"),
    ("qd19u03u@tempmail.cn", "AODwby2kN%yU"),
    ("ztldp7zj@tempmail.cn", "299YXQt61$S4"),
    ("1zbuy3g0@tempmail.cn", "!IOYVTL6B7wN"),
    ("5y150z2i@tempmail.cn", "&*gjSJ5^yZo5"),
    ("oa0qn6yy@tempmail.cn", "Ydd$GTary%l1"),
    ("th618pi7@tempmail.cn", "jItURf*dIxnP"),
    ("zfar2fr4@tempmail.cn", "XOQrN2SwtZpq"),
    ("z8p1ieh2@tempmail.cn", "pVy1lOsoSgln"),
    ("7e7w1vlb@tempmail.cn", "KrJke2Oj3G!b"),
    ("m2d0l62t@tempmail.cn", "CEcEskdU*VK*"),
    ("m93hw29n@tempmail.cn", "pDgvdJtkYn5Y"),
    ("37j167l2@tempmail.cn", "!wTnOSiwQwOq"),
    ("3qe2qmtv@tempmail.cn", "C*$QsC*HC2C#"),
    ("7kqn64vu@tempmail.cn", "9ixe6bD81V*%"),
    ("bc41spfm@tempmail.cn", "&1BQV0CyMpFy"),
    ("yp8yykyt@tempmail.cn", "$Dq%GHb&rMi$"),
    ("9wpls22w@tempmail.cn", "$8!&phkXJA3f"),
    ("32be1drf@tempmail.cn", "H09A4X&F4gWc"),
    ("jg7vbi6e@tempmail.cn", "eCJBOP!7yHGb"),
    ("clsudczd@tempmail.cn", "RqlgcgK18hhC"),
    ("cwrh9ktf@tempmail.cn", "$Eyw14mJyOVi"),
    ("d5i3wyo6@tempmail.cn", "e6C!&Myy1hzD"),
    ("ob7qepgo@tempmail.cn", "VCjnWj^esFmm"),
    ("loz3qhwn@tempmail.cn", "dVrhIzd$afCc"),
    ("zrxdtflk@tempmail.cn", "iu@o2AzFKvEm"),
    ("g4jt75pe@tempmail.cn", "dMoq^dt0DxqK"),
    ("3ogwplu4@tempmail.cn", "$RKOTTyU%l59"),
    ("pus608wu@tempmail.cn", "$bBu3xp@M9i0"),
    ("x73i21tp@tempmail.cn", "yY4JnZ3YXFQ&"),
    ("e22un10x@tempmail.cn", "nAvuRhQSBB2z"),
    ("5aew5ut4@tempmail.cn", "F!hGPWxST$6t"),
    ("zmkniwcw@tempmail.cn", "pwOLg0%gZ8K3"),
    ("f8yxe9su@tempmail.cn", "mAEJFkb#z6wd"),
    ("roes67dn@tempmail.cn", "%2ORQ49GB^Sl"),
    ("3n7e5gsz@tempmail.cn", "FJ$$e67JDpNG"),
    ("h7hcu973@tempmail.cn", "jg8v^Vw0ufOR"),
    ("hdf380st@tempmail.cn", "VtFoJ4am4Jwh"),
    ("k18d4rbr@tempmail.cn", "vM%uYL9$skpL"),
    ("j2j3kpmz@tempmail.cn", "s4DsGa2M3B%D"),
    ("0uaeumr4@tempmail.cn", "N3KY!2UjjQh#"),
    ("8kqlmxqf@tempmail.cn", "o7%JPNV@&Afl"),
    ("nsf3scoj@tempmail.cn", "p&2CwgoWTCRV"),
    ("eeioo6mo@tempmail.cn", "z4i&kOI0&F!L"),
    ("yipoe1wn@tempmail.cn", "S!68ghaoZx@V"),
    ("1o9foppw@tempmail.cn", "0DQnjfU6TylR"),
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


async def init_tables(session: aiohttp.ClientSession):
    """初始化数据库表"""
    await execute_sql(session, """
        CREATE TABLE IF NOT EXISTS email_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            key TEXT NOT NULL,
            is_assigned INTEGER DEFAULT 0,
            assigned_to TEXT,
            assigned_at TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    print("[OK] 数据库表已初始化")


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
        # 初始化表
        await init_tables(session)

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
