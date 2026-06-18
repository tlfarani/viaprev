import geopandas as gpd
import os
import sys

# 1. DEFINIÇÃO DE CAMINHOS LOCAIS
caminho_gdb = "risco.gdb"
arquivo_saida = "dados/areas_risco.parquet"

print(f"⏳ Passo 1: Lendo a pasta Geodatabase '{caminho_gdb}'...")
if not os.path.exists(caminho_gdb):
    print(f"❌ Erro: A pasta '{caminho_gdb}' não foi encontrada.")
    sys.exit()

try:
    gdf = gpd.read_file(caminho_gdb)
    print(f"✅ Base de risco carregada! Total de registros: {len(gdf)}")
except Exception as e:
    print(f"❌ Erro ao ler o Geodatabase: {e}")
    sys.exit()

# 2. SELEÇÃO DA CLASSIFICAÇÃO REAL (Grau de Risco + Descrição)
print("\n✂️ Passo 2: Extraindo matriz de criticidade (Grau de Risco + Processo)...")

# Força o cruzamento das colunas textuais da CPRM para gerar uma tag informativa
if 'grau_risco' in gdf.columns and 'descricao' in gdf.columns:
    print("🔍 Colunas 'grau_risco' e 'descricao' localizadas com sucesso!")
    # Cria uma classificação combinada, ex: "RISCO ALTO - DESLIZAMENTO DE ENCOSTA"
    gdf['grau_limpo'] = gdf['grau_risco'].astype(str).str.strip().str.upper()
    gdf['desc_limpa'] = gdf['descricao'].astype(str).str.strip().str.upper()
    gdf['classe_risco'] = gdf['grau_limpo'] + " (" + gdf['desc_limpa'] + ")"
elif 'grau_risco' in gdf.columns:
    gdf['classe_risco'] = gdf['grau_risco'].astype(str).str.strip().str.upper()
else:
    gdf['classe_risco'] = "PERIGO GEOLÓGICO"

# Mantém apenas a coluna corrigida e a geometria
colunas_essenciais = ['classe_risco', 'geometry']
gdf_filtrado = gdf[colunas_essenciais].copy()
gdf_filtrado = gdf_filtrado[gdf_filtrado.geometry.notna()]

# 3. SIMPLIFICAÇÃO GEOMÉTRICA (Tolerância: 150 metros)
print("\n⚡ Passo 3: Otimizando polígonos de risco (Tolerância: 150m)...")
gdf_m = gdf_filtrado.to_crs(epsg=5880)
gdf_m['geometry'] = gdf_m.geometry.simplify(tolerance=150, preserve_topology=True)
gdf_final = gdf_m.to_crs(epsg=4326)

# 4. EXPORTAÇÃO
os.makedirs("dados", exist_ok=True)
print(f"💾 Passo 4: Exportando arquivo otimizado para '{arquivo_saida}'...")
gdf_final.to_parquet(arquivo_saida)

tamanho_mb = os.path.getsize(arquivo_saida) / (1024 * 1024)
print(f"\n✨ SUCESSO! Base de áreas de risco recalibrada com {tamanho_mb:.2f} MB.")