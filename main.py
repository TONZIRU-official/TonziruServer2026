import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
import random

TOKEN = "MTQ0Njc2Mjg4NDgzODMzMDQ0MA.G3MjT6.f3YrTLmMWuOt9r2fEQiodGk2PcUTybOxzMgsus"
GUILD_ID = 1446758581146878154

# DB 接続
conn = sqlite3.connect("hachoshi.db")
cur = conn.cursor()

# ---------- DB セットアップ -----------
cur.execute("""
CREATE TABLE IF NOT EXISTS economy (
    user_id INTEGER PRIMARY KEY,
    balance INTEGER DEFAULT 0
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    price INTEGER,
    stock INTEGER
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS inventory (
    user_id INTEGER,
    item_id INTEGER,
    amount INTEGER DEFAULT 0,
    PRIMARY KEY (user_id, item_id)
)
""")

conn.commit()

# ---------- Bot セットアップ ----------
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)


# ----------- ユーティリティ ------------
def get_balance(uid):
    cur.execute("SELECT balance FROM economy WHERE user_id=?", (uid,))
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute("INSERT INTO economy(user_id, balance) VALUES(?,0)", (uid,))
    conn.commit()
    return 0

def add_money(uid, amount):
    bal = get_balance(uid)
    cur.execute("UPDATE economy SET balance=? WHERE user_id=?", (bal + amount, uid))
    conn.commit()

def add_inventory(uid, item_id, amount):
    cur.execute("SELECT amount FROM inventory WHERE user_id=? AND item_id=?", (uid, item_id))
    row = cur.fetchone()
    if row:
        cur_amount = row[0]
        cur.execute("UPDATE inventory SET amount=? WHERE user_id=? AND item_id=?", 
                    (cur_amount + amount, uid, item_id))
    else:
        cur.execute("INSERT INTO inventory VALUES (?,?,?)", (uid, item_id, amount))

    conn.commit()


# ============================
# 📌 経済コマンド
# ============================

@bot.tree.command(name="balance", description="所持金を確認します")
async def balance(interaction: discord.Interaction):
    bal = get_balance(interaction.user.id)
    await interaction.response.send_message(f"💰 所持金: **{bal} YTC**")

@bot.tree.command(name="work", description="八鳥市の仕事をして報酬をもらいます")
async def work(interaction: discord.Interaction):
    reward = random.randint(20, 60)
    add_money(interaction.user.id, reward)
    await interaction.response.send_message(
        f"🛠 お疲れ様です！報酬 **{reward} YTC** を獲得しました。"
    )

@bot.tree.command(name="pay", description="他の市民にお金を送ります")
@app_commands.describe(user="相手", amount="金額")
async def pay(interaction, user: discord.Member, amount: int):
    if amount <= 0:
        return await interaction.response.send_message("金額が不正です。")

    bal = get_balance(interaction.user.id)
    if bal < amount:
        return await interaction.response.send_message("残高が足りません。")

    add_money(interaction.user.id, -amount)
    add_money(user.id, amount)

    await interaction.response.send_message(
        f"💸 {user.mention} に **{amount} YTC** を送金しました。"
    )


# ============================
# 🏪 ショップ管理コマンド
# ============================

@bot.tree.command(name="shop_add", description="【管理者】商品を追加します")
@app_commands.describe(name="商品名", price="値段", stock="在庫")
async def shop_add(interaction, name: str, price: int, stock: int):
    if not interaction.user.guild_permissions.manage_guild:
        return await interaction.response.send_message("権限不足")

    cur.execute("INSERT INTO items(name, price, stock) VALUES(?,?,?)",
                (name, price, stock))
    conn.commit()

    await interaction.response.send_message(
        f"🆕 商品追加: **{name}**（{price} YTC、在庫 {stock}）"
    )

@bot.tree.command(name="shop_remove", description="【管理者】商品を削除します")
@app_commands.describe(item_id="商品ID")
async def shop_remove(interaction, item_id: int):
    if not interaction.user.guild_permissions.manage_guild:
        return await interaction.response.send_message("権限不足")

    cur.execute("DELETE FROM items WHERE id=?", (item_id,))
    conn.commit()

    await interaction.response.send_message(f"🗑 商品ID {item_id} を削除しました。")

@bot.tree.command(name="shop_setstock", description="【管理者】在庫を変更します")
@app_commands.describe(item_id="商品ID", stock="新しい在庫")
async def shop_setstock(interaction, item_id: int, stock: int):
    if not interaction.user.guild_permissions.manage_guild:
        return await interaction.response.send_message("権限不足")

    cur.execute("UPDATE items SET stock=? WHERE id=?", (stock, item_id))
    conn.commit()

    await interaction.response.send_message(
        f"📦 商品ID {item_id} の在庫を {stock} に設定しました。"
    )


# ============================
# 🏪 ショップパネル（ボタン付き）
# ============================

class BuyButton(discord.ui.View):
    def __init__(self, item_id):
        super().__init__(timeout=None)
        self.item_id = item_id

    @discord.ui.button(label="購入する", style=discord.ButtonStyle.green)
    async def buy(self, interaction: discord.Interaction, button: discord.ui.Button):
        uid = interaction.user.id

        # 商品情報取得
        cur.execute("SELECT name, price, stock FROM items WHERE id=?", (self.item_id,))
        row = cur.fetchone()

        if not row:
            return await interaction.response.send_message("商品が存在しません。", ephemeral=True)

        name, price, stock = row

        if stock <= 0:
            return await interaction.response.send_message("在庫がありません。", ephemeral=True)

        bal = get_balance(uid)
        if bal < price:
            return await interaction.response.send_message("所持金が足りません。", ephemeral=True)

        # 購入処理
        add_money(uid, -price)
        add_inventory(uid, self.item_id, 1)

        cur.execute("UPDATE items SET stock=? WHERE id=?", (stock - 1, self.item_id))
        conn.commit()

        await interaction.response.send_message(
            f"🛒 購入完了！\n**{name}** を獲得しました！（残金: {bal - price} YTC）",
            ephemeral=True
        )


@bot.tree.command(name="shop_panel", description="【管理者】ショップパネルを生成します")
async def shop_panel(interaction):
    if not interaction.user.guild_permissions.manage_guild:
        return await interaction.response.send_message("権限不足")

    cur.execute("SELECT id, name, price, stock FROM items")
    rows = cur.fetchall()

    if not rows:
        return await interaction.response.send_message("商品がありません。")

    for item in rows:
        item_id, name, price, stock = item

        embed = discord.Embed(
            title=f"商品ID {item_id}: {name}",
            description=f"💰 **{price} YTC**\n📦 在庫: {stock}",
            color=0x00aaff
        )
        view = BuyButton(item_id)

        await interaction.channel.send(embed=embed, view=view)

    await interaction.response.send_message("ショップパネルを設置しました。", ephemeral=True)


# ============================
# 起動
# ============================

@bot.event
async def on_ready():
    synced = await bot.tree.sync()
    print(f"Synced {len(synced)} commands.")


bot.run(TOKEN)
