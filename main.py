import discord
from discord.ext import commands
from discord import app_commands
import datetime
from typing import Optional

# Configuração dos Intents do Bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_command_prefix="!", intents=intents)

# Banco de dados simulado em memória (Para produção, use SQLite ou MongoDB)
DATA = {
    "cards": {
        1: {"nome": "Cristal Opaco", "raridade": "Comum", "valor": 150, "imagem": "https://i.imgur.com/your_pixel_art_crystal.png"}
    },
    "usuarios": {},
    "config": {
        "roleta_tempo": 150, # 2 horas e 30 minutos em minutos
        "roleta_custo": 200,
        "diario_recompensa": 500
    },
    "raridades": {
        "Comum": {"cor": discord.Color.blue(), "chance": 70},
        "Raro": {"cor": discord.Color.green(), "chance": 20},
        "Épico": {"cor": discord.Color.purple(), "chance": 8},
        "Lendário": {"cor": discord.Color.gold(), "chance": 2}
    }
}

# Funções auxiliares para gerenciar o "Banco de Dados"
def obter_usuario(user_id):
    if user_id not in DATA["usuarios"]:
        DATA["usuarios"][user_id] = {
            "saldo": 1000,
            "inventario": {}, # {card_id: quantidade}
            "ultimo_diario": None,
            "ultima_roleta": None
        }
    return DATA["usuarios"][user_id]

# --- VISUAL: Botão de Venda Interativo ---
class BotaoVender(discord.ui.View):
    def __init__(self, card_id: int, user_id: int):
        super().__init__(timeout=60)
        self.card_id = card_id
        self.user_id = user_id

    @discord.ui.button(label="Vender", style=discord.ButtonStyle.success)
    async def vender_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Você não pode vender o item de outra pessoa!", ephemeral=True)
            return

        user_data = obter_usuario(self.user_id)
        card = DATA["cards"].get(self.card_id)

        if not card or user_data["inventario"].get(self.card_id, 0) <= 0:
            await interaction.response.send_message("Você não possui mais esse item para vender.", ephemeral=True)
            return

        # Processa a venda
        user_data["inventario"][self.card_id] -= 1
        user_data["saldo"] += card["valor"]
        
        # Desabilita o botão após a venda bem-sucedida
        button.disabled = True
        button.label = "Vendido!"
        await interaction.message.edit(view=self)
        
        await interaction.response.send_message(f"💰 Você vendeu ** por **${card['valor']}**!", ephemeral=True)

# --- EVENTO DE INICIALIZAÇÃO ---
@bot.event
async def on_ready():
    print(f"Bot iniciado com sucesso como {bot.user.name}")
    try:
        synced = await bot.tree.sync()
        print(f"Sincronizados {len(synced)} comandos de barra!")
    except Exception as e:
        print(f"Erro ao sincronizar comandos: {e}")

# =====================================================================
# COMANDOS DE ADMINISTRADOR (Modificáveis)
# =====================================================================

# Verificação simples de ADM (Pode ser alterado para checar cargos específicos)
def e_admin(interaction: discord.Interaction) -> bool:
    return interaction.user.guild_permissions.administrator

@bot.tree.command(name="criar-carta", description="[ADM] Cria uma nova carta para o sistema")
@app_commands.check(e_admin)
async def criar_carta(interaction: discord.Interaction, nome: str, raridade: str, valor: int, imagem: str):
    if raridade not in DATA["raridades"]:
        await interaction.response.send_message("Raridade inválida! Escolha entre Comum, Raro, Épico ou Lendário.", ephemeral=True)
        return
        
    novo_id = max(DATA["cards"].keys(), default=0) + 1
    DATA["cards"][novo_id] = {"nome": nome, "raridade": raridade, "valor": valor, "imagem": imagem}
    await interaction.response.send_message(f"Carta **{nome}** ({raridade}) criada com sucesso! ID: {novo_id}")

@bot.tree.command(name="dar-dinheiro", description="[ADM] Dá dinheiro a um usuário")
@app_commands.check(e_admin)
async def dar_dinheiro(interaction: discord.Interaction, usuario: discord.User, quantia: int):
    user_data = obter_usuario(usuario.id)
    user_data["saldo"] += quantia
    await interaction.response.send_message(f"Adicionados **${quantia}** para {usuario.mention}.")

@bot.tree.command(name="dar-carta", description="[ADM] Dá uma carta específica para um usuário")
@app_commands.check(e_admin)
async def dar_carta(interaction: discord.Interaction, usuario: discord.User, card_id: int):
    if card_id not in DATA["cards"]:
        await interaction.response.send_message("ID da carta não encontrado.", ephemeral=True)
        return
    user_data = obter_usuario(usuario.id)
    user_data["inventario"][card_id] = user_data["inventario"].get(card_id, 0) + 1
    await interaction.response.send_message(f"Carta adicionada ao inventário de {usuario.mention}.")

@bot.tree.command(name="definir-roleta", description="[ADM] Configura o tempo de cooldown e custo da roleta")
@app_commands.check(e_admin)
async def definir_roleta(interaction: discord.Interaction, minutos: int, custo: int):
    DATA["config"]["roleta_tempo"] = minutos
    DATA["config"]["roleta_custo"] = custo
    await interaction.response.send_message(f"Roleta atualizada! Cooldown: {minutos}m | Custo extra: ${custo}")

# =====================================================================
# COMANDOS DE USUÁRIOS (Jogabilidade e Visual)
# =====================================================================

@bot.tree.command(name="roleta", description="Gire a roleta de cartas. Grátis a cada 2h30min ou pague $200")
async def roleta(interaction: discord.Interaction):
    user_data = obter_usuario(interaction.user.id)
    agora = datetime.datetime.now()
    
    cooldown_minutos = DATA["config"]["roleta_tempo"]
    custo_pago = DATA["config"]["roleta_custo"]
    
    usar_pago = False
    
    if user_data["ultima_roleta"]:
        tempo_passado = agora - user_data["ultima_roleta"]
        minutos_passados = tempo_passado.total_seconds() / 60
        
        if minutos_passados < cooldown_minutos:
            if user_data["saldo"] >= custo_pago:
                user_data["saldo"] -= custo_pago
                usar_pago = True
            else:
                tempo_restante = int(cooldown_minutos - minutos_passados)
                await interaction.response.send_message(f"⏳ Você precisa esperar mais {tempo_restante} minutos ou ter **${custo_pago} para girar novamente!", ephemeral=True)
                return

    # Sorteio simples de uma carta registrada
    import random
    if not DATA["cards"]:
        await interaction.response.send_message("Nenhuma carta cadastrada no bot ainda.", ephemeral=True)
        return
        
    card_id = random.choice(list(DATA["cards"].keys()))
    card = DATA["cards"][card_id]
    
    # Atualiza inventário do usuário
    user_data["inventario"][card_id] = user_data["inventario"].get(card_id, 0) + 1
    if not usar_pago:
        user_data["ultima_roleta"] = agora

    # Montagem do Design idêntico ao solicitado
    cor_raridade = DATA["raridades"].get(card["raridade"], {}).get("cor", discord.Color.blue())
    
    embed = discord.Embed(
        title="Você acabou de ganhar:",
        description=f"###  ({card['raridade']}) x1", inline=False)
    embed.set_footer(text="🍀 Vote no Top.gg para bônus de sorte! Use /votar sequencia para saber mais")

    # Envia a mensagem acoplada com o botão de Venda rápida
    view = BotaoVender(card_id=card_id, user_id=interaction.user.id)
    await interaction.response.send_message(embed=embed, view=view)

@bot.tree.command(name="inventario", description="Mostra suas cartas e saldo atual")
async def inventario(interaction: discord.Interaction):
    user_data = obter_usuario(interaction.user.id)
    
    embed = discord.Embed(title=f"🎒 Inventário de {interaction.user.name}", color=discord.Color.dark_purple())
    embed.add_field(name="💰 Saldo Atual", value=f"${user_data['saldo']}", inline=False)
    
    itens_str = ""
    for card_id, qtd in user_data["inventario"].items():
        if qtd > 0:
            card = DATA["cards"].get(card_id)
            if card:
                itens_str += f"• ** ({card['raridade']}) — x{qtd}\n"
                
    embed.add_field(name="🎴 Cartas Colecionadas", value=itens_str if itens_str else "Nenhuma carta no inventário.", inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="diario", description="Resgate sua recompensa diária de moedas")
async def diario(interaction: discord.Interaction):
    user_data = obter_usuario(interaction.user.id)
    agora = datetime.datetime.now()
    
    if user_data["ultimo_diario"]:
        if (agora - user_data["ultimo_diario"]).days < 1:
            await interaction.response.send_message("❌ Você já resgatou seu prêmio diário hoje! Volte amanhã.", ephemeral=True)
            return
            
    recompensa = DATA["config"]["diario_recompensa"]
    user_data["saldo"] += recompensa
    user_data["ultimo_diario"] = agora
    
    await interaction.response.send_message(f"📆 Recompensa diária coletada! **+${recompensa}** adicionados ao seu saldo.")

# --- Inicialização do Bot com o Token ---
# Substitua pelo Token oficial gerado no Discord Developer Portal
bot.run("MTUxNjIyMTA3NTQ1MTY3ODg2MQ.GNXOan.HP-hxlKk5ZcNqTsS5goAZWY0s1GrL__nJXgQfE")
