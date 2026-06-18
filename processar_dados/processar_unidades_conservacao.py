import geopandas as gpd
import os

# 1. DEFINIÇÃO DE CAMINHOS
arquivo_zip = "UCs.zip"
arquivo_saida = "unidades_conservacao.parquet"

print(f"⏳ Passo 1: Lendo '{arquivo_zip}' direto da pasta atual...")
try:
    gdf = gpd.read_file(f"zip://{arquivo_zip}")
    print(f"✅ Base de Unidades de Conservação carregada! Registros originais: {len(gdf)}")
except Exception as e:
    print(f"❌ Erro ao ler '{arquivo_zip}': {e}")
    exit()

# 2. IDENTIFICAÇÃO CORRIGIDA PELA COLUNA 'NOME_UC1'
print("\n✂️ Passo 2: Padronizando atributos com base na coluna 'NOME_UC1'...")

# Força o mapeamento direto para a coluna real identificada no seu console
if 'NOME_UC1' in gdf.columns:
    print("🔍 Coluna 'NOME_UC1' localizada com sucesso!")
    gdf['nome_uc'] = gdf['NOME_UC1'].astype(str).str.strip().str.upper()
else:
    # Caso rode em outra base no futuro, mantém a busca inteligente por aproximação
    col_nome = [col for col in gdf.columns if 'nome' in col.lower() or 'uc' in col.lower()]
    if col_nome:
        print(f"🔍 Coluna identificada por aproximação: '{col_nome[0]}'")
        gdf['nome_uc'] = gdf[col_nome[0]].astype(str).str.strip().str.upper()
    else:
        gdf['nome_uc'] = "UNIDADE DE CONSERVAÇÃO"

# Mantém estritamente o nome real da UC e a geometria
colunas_essenciais = ['nome_uc', 'geometry']
gdf_filtrado = gdf[colunas_essenciais].copy()
gdf_filtrado = gdf_filtrado[gdf_filtrado.geometry.notna()]

# 3. SIMPLIFICAÇÃO GEOMÉTRICA DE POLÍGONOS (Tolerância: 150 metros)
print("\n⚡ Passo 3: Otimizando os polígonos das UCs (Tolerância: 150m)...")
gdf_m = gdf_filtrado.to_crs(epsg=5880)
gdf_m['geometry'] = gdf_m.geometry.simplify(tolerance=150, preserve_topology=True)
gdf_final = gdf_m.to_crs(epsg=4326)

# 4. EXPORTAÇÃO PARA GEOPARQUET
os.makedirs("dados", exist_ok=True)
print(f"\n💾 Passo 4: Exportando base otimizada para '{arquivo_saida}'...")
gdf_final.to_parquet(arquivo_saida)

tamanho_mb = os.path.getsize(arquivo_saida) / (1024 * 1024)
print(f"\n✨ SUCESSO! Camada de Unidades de Conservação corrigida.")
print(f"📦 Tamanho final do arquivo unificado: {tamanho_mb:.2f} MB")