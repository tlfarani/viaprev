#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed Jun 17 18:35:27 2026

@author: farani
"""

import os
import sys

# --- CORREÇÃO CIRÚRGICA DE PROJEÇÃO PARA O MAC (Bypass do erro de context database) ---
try:
    import pyproj
    caminho_dinamico_proj = os.path.join(sys.prefix, "share", "proj")
    if os.path.exists(caminho_dinamico_proj):
        pyproj.datadir.set_data_dir(caminho_dinamico_proj)
        os.environ["PROJ_DATA"] = caminho_dinamico_proj
        os.environ["PROJ_LIB"] = caminho_dinamico_proj
except Exception as e:
    print(f"⚠️ Nota ao configurar pyproj: {e}")

import geopandas as gpd
import pandas as pd

print("⏳ Lendo e padronizando as bases do GeoDNIT...")

# 1. Carregar e classificar cada camada
try:
    manutencao = gpd.read_file("zip://vw_epl_manutencao.zip")
    manutencao['tipo_logistico'] = 'Oficina de Manutenção'
except Exception as e:
    print(f"Erro ao ler manutenção: {e}")
    manutencao = gpd.GeoDataFrame()

try:
    patios = gpd.read_file("zip://vw_epl_patios.zip")
    patios['tipo_logistico'] = 'Pátio Operacional'
except Exception as e:
    print(f"Erro ao ler pátios: {e}")
    patios = gpd.GeoDataFrame()

try:
    terminais = gpd.read_file("zip://vw_epl_terminais.zip")
    terminais['tipo_logistico'] = 'Terminal de Cargas'
except Exception as e:
    print(f"Erro ao ler terminais: {e}")
    terminais = gpd.GeoDataFrame()

# 2. Unificar os GeoDataFrames em uma lista para tratamento
camadas = [manutencao, patios, terminais] # terminais mapeado como terminais
camadas_validas = [c for c in [manutencao, patios, terminais] if not c.empty]

if not camadas_validas:
    print("❌ Nenhuma camada foi carregada com sucesso. Verifique os nomes dos arquivos zip.")
    exit()

# 3. Mapeamento Direto com base na Auditoria de Colunas
for g_df in camadas_validas:
    if 'Patio' in g_df.columns:
        g_df['nome'] = g_df['Patio'].astype(str).str.strip()
        print(f"🟢 Coluna 'Patio' mapeada com sucesso para {g_df['tipo_logistico'].iloc[0]}.")
    else:
        g_df['nome'] = "Instalação Sem Nome"

# 4. Concatenar todas as tabelas em um único GeoDataFrame unificado
print("🔄 Unificando bases em uma única malha de pontos...")
gdf_patios_oficinas = pd.concat([c[['nome', 'tipo_logistico', 'geometry']] for c in camadas_validas], ignore_index=True)
gdf_patios_oficinas = gpd.GeoDataFrame(gdf_patios_oficinas, geometry='geometry')

# 5. Garantir que o sistema de coordenadas é o WGS84 (EPSG:4326)
if gdf_patios_oficinas.crs is None:
    gdf_patios_oficinas.set_crs(epsg=4674, inplace=True)

# Converte para WGS84 exigido pelo Leaflet/Folium do ViaPrev
gdf_patios_oficinas = gdf_patios_oficinas.to_crs(epsg=4326)

# Limpeza para remover pontos corrompidos ou sem geometria
gdf_patios_oficinas = gdf_patios_oficinas[gdf_patios_oficinas.geometry.is_valid & ~gdf_patios_oficinas.geometry.is_empty]

# 6. Exportar para GeoParquet na pasta de dados do app
nome_saida = "dados/patios_oficinas.parquet"
gdf_patios_oficinas.to_parquet(nome_saida)

print(f"✅ Sucesso Absoluto! Arquivo '{nome_saida}' gerado com {len(gdf_patios_oficinas)} registros identificados.")