import geopandas as gpd
import geobr
import os
import sys
from shapely.geometry import box

# base obtida em: https://metadados.snirh.gov.br/geonetwork/srv/por/catalog.search#/metadata/f7b1fc91-f5bc-4d0d-9f4f-f4e5061e5d8f
# --- CORREÇÃO DE PROJEÇÃO PARA AMBIENTES MAC/ANACONDA ---
try:
    import pyproj
    caminho_proj = os.path.join(sys.prefix, "share", "proj")
    if os.path.exists(caminho_proj):
        pyproj.datadir.set_data_dir(caminho_proj)
        os.environ["PROJ_DATA"] = caminho_proj
        os.environ["PROJ_LIB"] = caminho_proj
except Exception as e:
    print(f"⚠️ Nota ao configurar pyproj: {e}")

arquivo_gpkg = "geoft_bho_2017_5k_curso_dagua.gpkg"
diretorio_saida = "dados/rios"
os.makedirs(diretorio_saida, exist_ok=True)

print("⏳ Passo 1: Carregando divisas dos estados brasileiros via geobr...")
estados = geobr.read_state()

print(f"⏳ Passo 2: Lendo a base hidrográfica massiva (674MB) da ANA '{arquivo_gpkg}'...")
if not os.path.exists(arquivo_gpkg):
    print(f"❌ Erro: O arquivo '{arquivo_gpkg}' não foi encontrado na pasta atual.")
    sys.exit()

try:
    # Lê a base da ANA mapeada no QGIS
    gdf_bruto = gpd.read_file(arquivo_gpkg)
    print(f"✅ Base nacional carregada! Total de segmentos lineares: {len(gdf_bruto)}")
except Exception as e:
    print(f"❌ Erro crítico ao ler o arquivo GPKG: {e}")
    sys.exit()

print("\n✂️ Passo 3: Mapeando colunas baseado na estrutura BHO/ANA...")

# Varredura inteligente para capturar o identificador correto da ANA verificado no QGIS
if 'cocursodag' in gdf_bruto.columns:
    gdf_bruto['nome_rio'] = "BHO COD: " + gdf_bruto['cocursodag'].astype(str)
elif 'NORIOCOMP' in gdf_bruto.columns:
    gdf_bruto['nome_rio'] = gdf_bruto['NORIOCOMP'].fillna("RIO SEM NOME").astype(str).str.strip().str.upper()
else:
    gdf_bruto['nome_rio'] = "CURSO D'ÁGUA INTEG"

# Mantém apenas as colunas essenciais para garantir leveza no Streamlit Cloud
gdf_saneado = gdf_bruto[['nome_rio', 'geometry']].copy()
gdf_saneado = gdf_saneado[gdf_saneado.geometry.notna()]

# Garante o CRS inicial (BHO costuma vir em SIRGAS 2000 EPSG:4674)
if gdf_saneado.crs is None:
    gdf_saneado.set_crs(epsg=4674, inplace=True)
gdf_wgs84 = gdf_saneado.to_crs(epsg=4326)

print("\n⚡ Passo 4: Iniciando fatiamento e otimização geométrica por UF...")
for idx, row_est in estados.iterrows():
    uf = row_est['abbrev_state'].lower()
    geom_est = row_est['geometry']
    
    print(f"🌊 Filtrando e cortando a malha hídrica do estado: {uf.upper()}...")
    
    # Otimização de RAM: Pré-filtra os rios usando a BBox do estado antes do corte rígido
    bbox_uf = box(*geom_est.bounds)
    gdf_sub = gdf_wgs84[gdf_wgs84.intersects(bbox_uf)].copy()
    
    if gdf_sub.empty:
        continue
        
    # Recorte topológico exato na fronteira político-administrativa do estado
    gdf_sub['geometry'] = gdf_sub.geometry.intersection(geom_est)
    gdf_sub = gdf_sub[~gdf_sub.geometry.is_empty]
    
    if gdf_sub.empty:
        continue
        
    # Simplificação métrica (Tolerância de 25 metros para equilibrar peso de arquivo e curvas reais)
    gdf_m = gdf_sub.to_crs(epsg=5880)
    gdf_m['geometry'] = gdf_m.geometry.simplify(tolerance=25, preserve_topology=True)
    gdf_final = gdf_m.to_crs(epsg=4326)
    
    # Purificação estrita de primitivos sólidos (Remove artefatos de nós gerados na intersecção)
    gdf_final = gdf_final[gdf_final.geometry.type.isin(['LineString', 'MultiLineString'])]
    
    if not gdf_final.empty:
        arquivo_saida = os.path.join(diretorio_saida, f"rios_{uf}.parquet")
        gdf_final.to_parquet(arquivo_saida)
        tamanho_mb = os.path.getsize(arquivo_saida) / (1024 * 1024)
        print(f"   💾 Salvo com sucesso! '{arquivo_saida}' | {len(gdf_final)} linhas | {tamanho_mb:.2f} MB")

print("\n✨ Base de Hidrografia de Alta Precisão da ANA fatiada e pronta para produção!")