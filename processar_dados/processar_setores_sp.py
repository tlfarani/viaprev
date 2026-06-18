#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed Jun 17 21:30:20 2026

@author: farani
"""

import geopandas as gpd
import os
import sys

# 1. DEFINIÇÃO DE CAMINHOS LOCAIS
arquivo_zip = "SP_setores_CD2022.zip"
arquivo_saida = "dados/setores_sp.parquet"

print(f"⏳ Passo 1: Carregando a malha massiva de setores de SP '{arquivo_zip}'...")
print("Nota: Como o arquivo é muito denso, a leitura pode levar de 1 a 2 minutos no Mac. Aguarde...")

if not os.path.exists(arquivo_zip):
    print(f"❌ Erro: O arquivo '{arquivo_zip}' não foi encontrado na pasta atual.")
    sys.exit()

try:
    # Lê a malha de setores censitários do IBGE direto do zip
    gdf = gpd.read_file(f"zip://{arquivo_zip}")
    print(f"✅ Base de dados carregada com sucesso!")
    print(f"📊 Total de micro-setores originais encontrados: {len(gdf)}")
except Exception as e:
    print(f"❌ Erro crítico ao ler os setores censitários: {e}")
    sys.exit()

# Inspeção das colunas no console para o Censo 2022
print("\n📋 Colunas originais encontradas na base do IBGE:")
print(list(gdf.columns))

# 2. SELEÇÃO CIRÚRGICA DE ATRIBUTOS SOCIOESPACIAIS
print("\n✂️ Passo 2: Limpando tabelas administrativas secundárias...")

# Identifica as colunas chaves do Censo 2022 do IBGE (ex: CD_SETOR, NM_MUN, TIPO)
col_codigo = [col for col in gdf.columns if 'cod' in col.lower() or 'setor' in col.lower()][0]
col_municipio = [col for col in gdf.columns if 'mun' in col.lower() and 'nome' in col.lower() or 'nm_mun' in col.lower()]

colunas_para_manter = []
gdf_limpo = gpd.GeoDataFrame()

if col_codigo:
    gdf_limpo['id_setor'] = gdf[col_codigo].astype(str)
    
if col_municipio:
    gdf_limpo['municipio'] = gdf[col_municipio[0]].astype(str).str.upper().str.strip()
else:
    gdf_limpo['municipio'] = "SÃO PAULO"

# Se houver a coluna 'TIPO' (que diferencia áreas urbanas de favelas/comunidades ou rurais)
col_tipo = [col for col in gdf.columns if 'tipo' in col.lower()]
if col_tipo:
    gdf_limpo['situacao'] = gdf[col_tipo[0]].astype(str).str.upper().str.strip()
else:
    gdf_limpo['situacao'] = "URBANO/RURAL"

# Restaura a geometria para o dataframe limpo
gdf_limpo['geometry'] = gdf.geometry
gdf_limpo = gdf_limpo[gdf_limpo.geometry.notna()]

# 3. SIMPLIFICAÇÃO GEOMÉTRICA CALIBRADA (Tolerância: 50 metros)
print("\n⚡ Passo 3: Aplicando simplificação geométrica controlada (Tolerância: 50m)...")
print("Removendo excesso de vértices em divisas de quadras urbanas...")
gdf_m = gdf_limpo.to_crs(epsg=5880) # Projeta temporariamente para metros

# Usamos 50m para não destruir o desenho das quadras vizinhas à linha do trem
gdf_m['geometry'] = gdf_m.geometry.simplify(tolerance=50, preserve_topology=True)
gdf_final = gdf_m.to_crs(epsg=4326)    # Retorna para graus (WGS84)

# 4. EXPORTAÇÃO COMPACTADA
os.makedirs("dados", exist_ok=True)
print(f"\n💾 Passo 4: Exportando base censitária compactada para '{arquivo_saida}'...")
gdf_final.to_parquet(arquivo_saida)

tamanho_mb = os.path.getsize(arquivo_saida) / (1024 * 1024)
print(f"\n✨ SUCESSO ABSOLUTO! Malha de vulnerabilidade socioespacial de SP finalizada.")
print(f"📦 Tamanho final do arquivo otimizado: {tamanho_mb:.2f} MB")