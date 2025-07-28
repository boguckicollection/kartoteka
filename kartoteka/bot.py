import os
from pathlib import Path
import discord
from discord.ext import commands, tasks
import csv
import asyncio
import datetime
import json
from dotenv import load_dotenv
from googleapiclient.discovery import build
from string import Template
import logging
from auction_utils import create_auction_product

load_dotenv()
logging.basicConfig(level=logging.INFO)

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN is not set")
GUILD_ID = int(os.getenv("DISCORD_GUILD_ID", "0"))
AUKCJE_KANAL_ID = int(os.getenv("AUKCJE_KANAL_ID", "0"))
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
ORDER_CHANNEL_ID = int(os.getenv("ORDER_CHANNEL_ID", "0"))
SELLER_CHANNEL_ID = int(os.getenv("SELLER_CHANNEL_ID", "0"))
OGLOSZENIA_KANAL_ID = int(os.getenv("OGLOSZENIA_KANAL_ID", "0"))
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
LIVE_CHAT_ID = os.getenv("LIVE_CHAT_ID")
BASE_IMAGE_URL = os.getenv("BASE_IMAGE_URL", "").rstrip("/")
SCANS_DIR = os.getenv("SCANS_DIR", "scans")

# Directory where aktualna_aukcja.html and aktualna_aukcja.json are stored
OUTPUT_DIR = Path("templates")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

bot = commands.Bot(command_prefix='/', intents=discord.Intents.all())

aukcje_kolejka = []
aktualna_aukcja = None
youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY) if YOUTUBE_API_KEY else None
yt_page_token = None
pending_orders = {}
pending_ok: dict[int, discord.User] = {}
seller_panel_msg: discord.Message | None = None
auction_msg: discord.Message | None = None
user_bid_messages: dict[int, discord.Message] = {}
announcement_msg: discord.Message | None = None
paused = False


def fetch_card_assets(nazwa: str, numer: str) -> tuple[str | None, str | None]:
    """Return card image URL from local scans if available."""
    name = nazwa.strip().lower().replace(" ", "_")
    num = numer.strip().lower().replace("/", "-")
    candidates = [
        f"{name}_{num}",
        f"{name}-{num}",
        f"{name} {num}",
        num,
    ]
    exts = [".jpg", ".png", ".jpeg"]

    base_dir = Path(SCANS_DIR)
    for root, _dirs, files in os.walk(base_dir):
        lower_map = {f.lower(): f for f in files}
        for cand in candidates:
            for ext in exts:
                fname = cand + ext
                if fname in lower_map:
                    rel = Path(root) / lower_map[fname]
                    rel_path = rel.relative_to(base_dir).as_posix()
                    url = f"{BASE_IMAGE_URL}/{rel_path}" if BASE_IMAGE_URL else str(rel)
                    return url, None

    logging.warning("Card image for %s (%s) not found", nazwa, numer)
    return None, None


async def fetch_card_assets_async(nazwa: str, numer: str) -> tuple[str | None, str | None]:
    """Asynchronously fetch card assets without blocking the event loop."""
    return await asyncio.to_thread(fetch_card_assets, nazwa, numer)


async def update_panel_embed():
    """Update or create the seller control panel embed."""
    channel = bot.get_channel(SELLER_CHANNEL_ID)
    if channel is None:
        return
    embed = discord.Embed(title="Panel aukcji", color=0x00FF90)
    queue_preview = "\n".join(
        f"{a.nazwa} ({a.numer})" for a in aukcje_kolejka[:5]
    ) or "Brak"
    embed.add_field(name="W kolejce", value=queue_preview, inline=False)
    if aktualna_aukcja:
        info = f"{aktualna_aukcja.nazwa} ({aktualna_aukcja.numer})\nCena: {aktualna_aukcja.cena:.2f} PLN"
        if aktualna_aukcja.zwyciezca:
            info += f"\nProwadzi: {aktualna_aukcja.zwyciezca}"
        if aktualna_aukcja.start_time:
            koniec = aktualna_aukcja.start_time + datetime.timedelta(seconds=aktualna_aukcja.czas)
            pozostalo = int((koniec - datetime.datetime.utcnow()).total_seconds())
            if pozostalo < 0:
                pozostalo = 0
            info += f"\nPozostało: {pozostalo}s"
        embed.add_field(name="Aktualna aukcja", value=info, inline=False)
    global seller_panel_msg
    if seller_panel_msg:
        try:
            await seller_panel_msg.edit(embed=embed, view=None)
        except discord.NotFound:
            seller_panel_msg = await channel.send(embed=embed, view=None)
    else:
        seller_panel_msg = await channel.send(embed=embed, view=None)



async def update_announcement_embed():
    """Uaktualnij lub utwórz embed z ogłoszeniem aukcji."""
    channel = bot.get_channel(OGLOSZENIA_KANAL_ID)
    if channel is None:
        return

    embed = discord.Embed(title="🔔 Ogłoszenie aukcji", color=0x00BFFF)

    if aktualna_aukcja:
        embed.add_field(
            name="Aktualna karta",
            value=f"{aktualna_aukcja.nazwa} ({aktualna_aukcja.numer})",
            inline=False,
        )
        embed.add_field(
            name="Cena",
            value=f"{aktualna_aukcja.cena:.2f} PLN",
            inline=True,
        )
        embed.add_field(
            name="Prowadzi",
            value=f"{aktualna_aukcja.zwyciezca or 'Brak'}",
            inline=True,
        )

        if aktualna_aukcja.start_time:
            koniec = aktualna_aukcja.start_time + datetime.timedelta(seconds=aktualna_aukcja.czas)
            pozostalo = int((koniec - datetime.datetime.utcnow()).total_seconds())
            pozostalo = max(pozostalo, 0)
            embed.add_field(
                name="Koniec za",
                value=f"{pozostalo}s",
                inline=True,
            )

        if aktualna_aukcja.obraz_url:
            embed.set_thumbnail(url=aktualna_aukcja.obraz_url)
    else:
        embed.add_field(name="Status", value="Brak aktywnej aukcji", inline=False)

    kolejka = "\n".join(f"{a.nazwa} ({a.numer})" for a in aukcje_kolejka[:5]) or "Brak"
    embed.add_field(name="W kolejce", value=kolejka, inline=False)

    global announcement_msg
    if announcement_msg:
        try:
            await announcement_msg.edit(embed=embed, view=None)
        except discord.NotFound:
            announcement_msg = await channel.send(embed=embed, view=None)
    else:
        announcement_msg = await channel.send(embed=embed, view=None)

async def announce_winner(aukcja: 'Aukcja'):
    """Wyświetl w ogłoszeniach wynik zakończonej aukcji."""
    channel = bot.get_channel(OGLOSZENIA_KANAL_ID)
    if channel is None:
        return
    embed = discord.Embed(
        title="✅ Aukcja zakończona",
        color=0xFF0000,
    )
    embed.add_field(
        name="Karta",
        value=f"{aukcja.nazwa} ({aukcja.numer})",
        inline=False,
    )
    embed.add_field(
        name="Cena końcowa",
        value=f"{aukcja.cena:.2f} PLN",
        inline=True,
    )
    embed.add_field(
        name="Zwycięzca",
        value=str(aukcja.zwyciezca or 'Brak'),
        inline=True,
    )
    if aukcja.obraz_url:
        embed.set_thumbnail(url=aukcja.obraz_url)
    if aukcje_kolejka:
        next_info = f"{aukcje_kolejka[0].nazwa} ({aukcje_kolejka[0].numer})"
        embed.add_field(
            name="Następna karta",
            value=next_info,
            inline=False,
        )
    else:
        embed.add_field(
            name="Następna karta",
            value="Brak kolejnych aukcji",
            inline=False,
        )
    global announcement_msg
    if announcement_msg:
        try:
            await announcement_msg.edit(embed=embed, view=None)
        except discord.NotFound:
            announcement_msg = await channel.send(embed=embed, view=None)
    else:
        announcement_msg = await channel.send(embed=embed, view=None)

async def notify_seller_end(aukcja: 'Aukcja'):
    """Przekaż wynik aukcji na kanał sprzedawcy."""
    channel = bot.get_channel(SELLER_CHANNEL_ID)
    if channel is None:
        return
    embed = discord.Embed(
        title="Informacja o zakończeniu aukcji",
        color=0xFF9900,
    )
    embed.add_field(name="Karta", value=f"{aukcja.nazwa} ({aukcja.numer})", inline=False)
    embed.add_field(name="Cena", value=f"{aukcja.cena:.2f} PLN", inline=True)
    embed.add_field(name="Zwycięzca", value=str(aukcja.zwyciezca or 'Brak'), inline=True)
    await channel.send(embed=embed)



async def update_auction_embed():
    """Aktualizuje embed licytacyjny z grafiką, ceną, prowadzącym i odliczaniem."""
    if not aktualna_aukcja or not auction_msg:
        return

    embed = discord.Embed(
        title=f"🎴 {aktualna_aukcja.nazwa} ({aktualna_aukcja.numer})",
        description=aktualna_aukcja.opis or "Brak opisu.",
        color=0xFFD700
    )

    embed.add_field(
        name="💸 Aktualna cena",
        value=f"**{aktualna_aukcja.cena:.2f} PLN**",
        inline=True
    )

    embed.add_field(
        name="➕ Kwota przebicia",
        value=f"{aktualna_aukcja.przebicie:.2f} PLN",
        inline=True
    )

    embed.add_field(
        name="🏆 Prowadzi",
        value=str(aktualna_aukcja.zwyciezca) if aktualna_aukcja.zwyciezca else "Brak",
        inline=True
    )

    if aktualna_aukcja.start_time:
        koniec = aktualna_aukcja.start_time + datetime.timedelta(seconds=aktualna_aukcja.czas)
        pozostalo = int((koniec - datetime.datetime.utcnow()).total_seconds())
        pozostalo = max(pozostalo, 0)
        embed.set_footer(text=f"⏳ Pozostało: {pozostalo}s")

    if aktualna_aukcja.logo_url:
        embed.set_author(name="Aukcja Pokémon", icon_url=aktualna_aukcja.logo_url)

    if aktualna_aukcja.obraz_url:
        embed.set_image(url=aktualna_aukcja.obraz_url)
    else:
        embed.add_field(name="Obraz", value="Brak zdjęcia karty", inline=False)

    await auction_msg.edit(embed=embed)

async def countdown_task(message: discord.Message, seconds: int):
    await update_auction_embed()
    await update_announcement_embed()
    remaining = float(seconds)
    interval = 0.5
    while remaining > 0:
        await asyncio.sleep(interval)
        remaining -= interval
        await update_auction_embed()
        await update_announcement_embed()
    await zakoncz_aukcje(message)
    await update_panel_embed()


async def start_next_auction(interaction: discord.Interaction | None = None):
    global aktualna_aukcja
    if paused:
        if interaction:
            await interaction.response.send_message("Panel wstrzymany.", ephemeral=True)
        return
    if aktualna_aukcja:
        if interaction:
            await interaction.response.send_message("Aukcja w toku.", ephemeral=True)
        return
    if not aukcje_kolejka:
        if interaction:
            await interaction.response.send_message("Brak aukcji w kolejce.", ephemeral=True)
        return
    if interaction:
        await interaction.response.defer()

    aktualna_aukcja = aukcje_kolejka.pop(0)
    aktualna_aukcja.start_time = datetime.datetime.utcnow()
    img, logo = await fetch_card_assets_async(
        aktualna_aukcja.nazwa, aktualna_aukcja.numer
    )
    aktualna_aukcja.obraz_url = img
    aktualna_aukcja.logo_url = logo
    logging.info(
        "Fetched assets for %s (%s): image=%s logo=%s",
        aktualna_aukcja.nazwa,
        aktualna_aukcja.numer,
        bool(img),
        bool(logo),
    )

    embed = discord.Embed(
        title=f"🏁 **{aktualna_aukcja.nazwa}** ({aktualna_aukcja.numer})",
        description=aktualna_aukcja.opis,
        color=0x00ff90,
    )
    embed.add_field(name="Numer", value=f"**{aktualna_aukcja.numer}**", inline=True)
    embed.add_field(name="Cena startowa", value=f"**{aktualna_aukcja.cena:.2f} PLN**", inline=True)
    embed.set_footer(text=f"⏳ Czas trwania: {aktualna_aukcja.czas} s")
    if aktualna_aukcja.logo_url:
        embed.set_thumbnail(url=aktualna_aukcja.logo_url)
    if aktualna_aukcja.obraz_url:
        embed.set_image(url=aktualna_aukcja.obraz_url)
    else:
        embed.add_field(name="Obraz", value="Brak zdjęcia karty", inline=False)

    channel = bot.get_channel(AUKCJE_KANAL_ID)
    msg = await channel.send(embed=embed, view=LicytacjaView())
    global auction_msg
    auction_msg = msg

    await update_auction_embed()

    zapisz_html(aktualna_aukcja)
    zapisz_json(aktualna_aukcja)

    bot.loop.create_task(countdown_task(msg, aktualna_aukcja.czas))
    await update_panel_embed()
    await update_announcement_embed()


@bot.event
async def on_ready():
    if youtube:
        check_youtube_chat.start()
    refresh_panel.start()

class Aukcja:
    def __init__(self, nazwa, numer, opis, cena_start, przebicie, czas):
        self.nazwa = nazwa
        self.numer = numer
        self.opis = opis
        # Support both comma and dot as decimal separators
        self.cena = float(str(cena_start).replace(",", "."))
        self.przebicie = float(str(przebicie).replace(",", "."))
        self.czas = int(czas)
        self.historia = []
        self.zwyciezca = None
        self.start_time = None
        self.order_number = None
        self.payment_method = None
        self.obraz_url = None
        self.logo_url = None
        self.product_url = None

    def licytuj(self, user):
        self.cena += self.przebicie
        self.historia.append((str(user), self.cena, datetime.datetime.utcnow().isoformat()))
        self.zwyciezca = user




def zapisz_html(aukcja: Aukcja, template_path: str = "templates/auction_template.html"):
    with open(template_path, encoding="utf-8") as f:
        template = Template(f.read())

    historia_html = ""
    last = list(reversed(aukcja.historia[-4:]))
    for i, (u, c, _t) in enumerate(last):
        strong = " font-weight:bold;" if i == 0 else ""
        historia_html += (
            f'<li style="{strong}"><span class="user">{u}</span> - '
            f'<span class="price">{c:.2f} PLN</span></li>'
        )

    html = template.safe_substitute(
        nazwa=aukcja.nazwa,
        numer=aukcja.numer,
        opis=aukcja.opis,
        cena=f"{aukcja.cena:.2f}",
        zwyciezca=aukcja.zwyciezca or "",
        historia=historia_html,
        obraz=aukcja.obraz_url or "",
    )

    out_html = OUTPUT_DIR / "aktualna_aukcja.html"
    with open(out_html, "w", encoding="utf-8") as f:
        f.write(html)

def zapisz_json(aukcja: Aukcja):
    next_nazwa = aukcje_kolejka[0].nazwa if aukcje_kolejka else None
    next_numer = aukcje_kolejka[0].numer if aukcje_kolejka else None
    dane = {
        "nazwa": aukcja.nazwa,
        "numer": aukcja.numer,
        "opis": aukcja.opis,
        "ostateczna_cena": aukcja.cena,
        "zwyciezca": str(aukcja.zwyciezca) if aukcja.zwyciezca else None,
        "historia": aukcja.historia[-4:],
        "start_time": (aukcja.start_time.isoformat() + "Z") if aukcja.start_time else None,
        "czas": aukcja.czas,
        "obraz": aukcja.obraz_url,
        "logo": aukcja.logo_url,
        "next_nazwa": next_nazwa,
        "next_numer": next_numer,
    }
    out_json = OUTPUT_DIR / 'aktualna_aukcja.json'
    with open(out_json, 'w', encoding='utf-8') as f:
        json.dump(dane, f, ensure_ascii=False, indent=2)

def generate_order_number() -> str:
    now = datetime.datetime.utcnow()
    prefix = f"AUC-{now.year}-{now.month:02d}-"
    os.makedirs('orders', exist_ok=True)
    counter_file = 'orders/counter.txt'
    try:
        with open(counter_file, 'r') as f:
            counter = int(f.read().strip())
    except FileNotFoundError:
        counter = 0
    counter += 1
    with open(counter_file, 'w') as f:
        f.write(str(counter))
    return prefix + f"{counter:04d}"

def zapisz_zamowienie(aukcja: Aukcja):
    order_number = generate_order_number()
    aukcja.order_number = order_number
    os.makedirs('orders', exist_ok=True)
    with open(f'orders/zamowienie_{order_number}.txt', 'w', encoding='utf-8') as f:
        f.write(
            f'Uzytkownik: {aukcja.zwyciezca}\n'
            f'Karta: {aukcja.nazwa}\n'
            f'Cena: {aukcja.cena:.2f}\n'
            f'Numer zamowienia: {order_number}\n'
        )

async def send_order_dm(aukcja: Aukcja):
    user = None
    if isinstance(aukcja.zwyciezca, discord.abc.User):
        user = aukcja.zwyciezca
    elif hasattr(aukcja.zwyciezca, "id"):
        try:
            user = await bot.fetch_user(aukcja.zwyciezca.id)
        except Exception:
            user = None
    if user is None:
        return
    message = (
        f"🎉 Gratulacje! Wygrałeś aukcję: **{aukcja.nazwa} ({aukcja.numer})** za **{aukcja.cena:.2f} PLN**.\n"
        "To jest test systemu. Czy wszystko jest OK?"
    )
    try:
        if aukcja.obraz_url:
            message += f"\n{aukcja.obraz_url}"
        if aukcja.product_url:
            message += f"\n{aukcja.product_url}"
        dm = await user.send(message)
        await dm.add_reaction("✅")
        pending_ok[dm.id] = user
    except discord.Forbidden:
        pass

async def notify_order_channel(aukcja: Aukcja):
    channel = bot.get_channel(ORDER_CHANNEL_ID)
    if channel is None:
        return
    embed = discord.Embed(
        title=f"Zamówienie {aukcja.order_number}",
        description=f"{aukcja.nazwa} ({aukcja.numer})",
        color=0x00FF00,
    )
    if aukcja.obraz_url:
        embed.set_image(url=aukcja.obraz_url)
    else:
        embed.add_field(name="Obraz", value="Brak zdjęcia karty", inline=False)
    embed.add_field(name="Cena", value=f"{aukcja.cena:.2f} PLN", inline=False)
    if aukcja.payment_method:
        embed.add_field(name="Metoda płatności", value=aukcja.payment_method, inline=False)
    embed.add_field(name="Kupujący", value=str(aukcja.zwyciezca), inline=False)
    embed.set_footer(text="Status: oczekuje na potwierdzenie")
    msg = await channel.send(embed=embed)
    pending_orders[msg.id] = aukcja
    await msg.add_reaction("✅")

async def zakoncz_aukcje(msg):
    global aktualna_aukcja, auction_msg
    if aktualna_aukcja:
        zapisz_html(aktualna_aukcja)
        zapisz_json(aktualna_aukcja)

        embed = discord.Embed(
            title=f"✅ Aukcja zako\u0144czona: {aktualna_aukcja.nazwa}",
            color=0xff0000,
        )
        embed.add_field(
            name="💵 Cena ko\u0144cowa",
            value=f"**{aktualna_aukcja.cena:.2f} PLN**",
            inline=True,
        )
        embed.add_field(
            name="🏆 Zwyci\u0119zca",
            value=f"**{aktualna_aukcja.zwyciezca or 'Brak'}**",
            inline=True,
        )
        if aktualna_aukcja.logo_url:
            embed.set_thumbnail(url=aktualna_aukcja.logo_url)
        if aktualna_aukcja.obraz_url:
            embed.set_image(url=aktualna_aukcja.obraz_url)
        try:
            await msg.edit(embed=embed, view=None)
        except discord.NotFound:
            pass

        await announce_winner(aktualna_aukcja)
        await notify_seller_end(aktualna_aukcja)

        if aktualna_aukcja.zwyciezca:
            try:
                await msg.channel.send(
                    f"Gratuluję!\nwygrał: {aktualna_aukcja.zwyciezca}\nczekaj na wiadomość DM"
                )
            except discord.HTTPException:
                pass

        if aukcje_kolejka:
            next_text = f"Za chwilę kolejna karta: {aukcje_kolejka[0].nazwa} ({aukcje_kolejka[0].numer})"
        else:
            next_text = "Brak kolejnych kart"
        try:
            await msg.channel.send(f"Aukcja zakończona. {next_text}")
        except discord.HTTPException:
            pass

        if aktualna_aukcja.zwyciezca:
            zapisz_zamowienie(aktualna_aukcja)
            aktualna_aukcja.product_url = await asyncio.to_thread(
                create_auction_product, aktualna_aukcja
            )
            bot.loop.create_task(send_order_dm(aktualna_aukcja))

        # finalize user bid messages
        for m in list(user_bid_messages.values()):
            try:
                await m.edit(content=f"Aukcja zakończona. Cena końcowa: {aktualna_aukcja.cena:.2f} PLN")
            except (discord.NotFound, discord.HTTPException):
                pass
        user_bid_messages.clear()

        aktualna_aukcja = None
        auction_msg = None
        await update_panel_embed()



class LicytacjaView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label='🔼 LICYTUJ', style=discord.ButtonStyle.green)
    async def licytuj(self, interaction: discord.Interaction, button: discord.ui.Button):
        global aktualna_aukcja
        if not aktualna_aukcja:
            await interaction.response.send_message("Brak aktywnej aukcji.", ephemeral=True)
            return
        if aktualna_aukcja.start_time:
            end_time = aktualna_aukcja.start_time + datetime.timedelta(seconds=aktualna_aukcja.czas)
            if datetime.datetime.utcnow() >= end_time:
                await interaction.response.send_message("Aukcja już zakończona.", ephemeral=True)
                return
        aktualna_aukcja.licytuj(interaction.user)
        zapisz_html(aktualna_aukcja)
        zapisz_json(aktualna_aukcja)
        content = f"✅ Twoja oferta: {aktualna_aukcja.cena:.2f} PLN"
        msg = user_bid_messages.get(interaction.user.id)
        if msg:
            await interaction.response.defer()
            try:
                await msg.edit(content=content)
            except discord.NotFound:
                msg = None
        if not msg:
            await interaction.response.send_message(content, ephemeral=True)
            try:
                user_bid_messages[interaction.user.id] = await interaction.original_response()
            except Exception:
                pass
        await update_panel_embed()
        await update_auction_embed()
        await update_announcement_embed()



@tasks.loop(seconds=1)
async def refresh_panel():
    await update_panel_embed()

@tasks.loop(seconds=5)
async def check_youtube_chat():
    global yt_page_token
    if not youtube or not LIVE_CHAT_ID or not aktualna_aukcja:
        return
    try:
        resp = youtube.liveChatMessages().list(
            liveChatId=LIVE_CHAT_ID,
            part="snippet,authorDetails",
            pageToken=yt_page_token
        ).execute()
        yt_page_token = resp.get("nextPageToken")
        for item in resp.get("items", []):
            msg_text = item["snippet"]["displayMessage"].lower()
            if "!bit" in msg_text:
                user = item["authorDetails"]["displayName"]
                aktualna_aukcja.licytuj(user)
                zapisz_html(aktualna_aukcja)
                zapisz_json(aktualna_aukcja)
                await update_panel_embed()
                await update_auction_embed()
                await update_announcement_embed()
    except Exception:
        pass


@bot.event
async def on_reaction_add(reaction, user):
    if user.bot:
        return
    if reaction.message.id in pending_orders and str(reaction.emoji) == "✅" and user.id == ADMIN_ID:
        aukcja = pending_orders.pop(reaction.message.id)
        if isinstance(aukcja.zwyciezca, discord.User):
            try:
                await aukcja.zwyciezca.send(
                    f"✅ Twoje zamówienie {aukcja.order_number} zostało potwierdzone.\nWkrótce karta trafi do wysyłki. Dzięki za udział w licytacji!"
                )
            except discord.Forbidden:
                pass
    if reaction.message.id in pending_ok and str(reaction.emoji) == "✅" and user == pending_ok.get(reaction.message.id):
        pending_ok.pop(reaction.message.id, None)
        channel = bot.get_channel(SELLER_CHANNEL_ID)
        if channel:
            await channel.send(f"Użytkownik {user} zaznaczył OK.")


def run_bot() -> None:
    """Start the Discord bot."""
    bot.run(TOKEN)
