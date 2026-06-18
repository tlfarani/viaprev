import geopandas as gpd
import os
import sys

# 1. DEFINIÇÃO DE CAMINHOS LOCAIS
# Usamos o ponteiro '!' para entrar na pasta interna do zip que descobrimos na auditoria
arquivo_zip = "zip://BaseFerro.zip!BaseFerro/BaseFerro.shp"
arquivo_saida = "dados/malha_ferroviaria.parquet"

print("⏳ Passo 1: Lendo a base ferroviária nacional de 'BaseFerro.zip'...")
if not os.path.exists("BaseFerro.zip"):
    print("❌ Erro: O arquivo 'BaseFerro.zip' não foi encontrado na pasta atual.")
    sys.exit()

try:
    gdf_bruto = gpd.read_file(arquivo_zip)
    print(f"✅ Base carregada com sucesso! Total de segmentos: {len(gdf_bruto)}")
except Exception as e:
    print(f"❌ Erro ao ler a pasta interna do ZIP: {e}")
    sys.exit()

# 2. EXTRAÇÃO E PADRONIZAÇÃO DE ATRIBUTOS
print("\n✂️ Passo 2: Saneando colunas e vinculando as concessionárias...")

# Pré-processamos as colunas em séries limpas
concessionaria = gdf_bruto['nome'].fillna("SEM CONCESSIONÁRIA INFORMADA").astype(str).str.strip().str.upper()
codigo_pnv = gdf_bruto['sigla'].fillna("SEM INFO").astype(str).str.strip().str.upper()
status = gdf_bruto['tip_situac'].fillna("NÃO INFORMADO").astype(str).str.strip()

# CORREÇÃO CRÍTICA: Instanciamos o GeoDataFrame injetando os dados e a geometria juntos
gdf_limpo = gpd.GeoDataFrame(
    {
        'concessionaria': concessionaria,
        'codigo_pnv': codigo_pnv,
        'status': status
    },
    geometry=gdf_bruto.geometry,
    crs=gdf_bruto.crs
)

# Remove registros sem geometria válida por precaução
gdf_limpo = gdf_limpo[gdf_limpo.geometry.notna()]

# 3. CONVERSÃO DE COORDENADAS DO SISTEMA ORIGINAL PARA WGS84
print("\n🌐 Passo 3: Ajustando sistema de coordenadas para o padrão do mapa (WGS84)...")
gdf_final = gdf_limpo.to_crs(epsg=4326)

# 4. EXPORTAÇÃO PARA GEOPARQUET
os.makedirs("dados", exist_ok=True)
print(f"💾 Passo 4: Exportando malha de grafos higienizada para '{arquivo_saida}'...")
gdf_final.to_parquet(arquivo_saida)

# Cálculo do ganho de armazenamento obtido
tamanho_mb = os.path.getsize(arquivo_saida) / (1024 * 1024)
print(f"\n✨ SUCESSO! Base ferroviária consolidada com as Concessionárias reais.")
print(f"📦 Tamanho final do arquivo otimizado: {tamanho_mb:.2f} MB")
