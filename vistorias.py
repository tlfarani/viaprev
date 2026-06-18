import streamlit as st
import geopandas as gpd
import geobr
import networkx as nx
import folium
from streamlit_folium import st_folium
from shapely.ops import substring
from shapely.geometry import LineString, Point, box
import os

# Configuração da página do Streamlit
st.set_page_config(
    layout="wide", 
    page_title="Planejador Nacional de Vistoria Ferroviária",
    page_icon="🚊"
)

st.title("🚊 Planejador de Vistoria Ferroviária com Matriz de Risco")
st.markdown("Análise preditiva de criticidade socioambiental baseada em Combinação Linear Ponderada (Análise Multicritério).")

# --- 1. INICIALIZAÇÃO DA MEMÓRIA DO APP ---
if "dados_calculados" not in st.session_state:
    st.session_state.dados_calculados = None

# --- 2. CARREGAMENTO DOS DADOS NACIONAIS BASE ---
@st.cache_data(show_spinner=False)
def carregar_bases_nacionais():
    sedes_municipios = geobr.read_municipal_seat()
    try:
        malha_ferroviaria = gpd.read_parquet("dados/malha_ferroviaria.parquet")
        if malha_ferroviaria.crs is None:
            malha_ferroviaria.set_crs(epsg=4326, inplace=True)
    except Exception:
        st.sidebar.error("❌ Arquivo 'dados/malha_ferroviaria.parquet' ausente!")
        malha_ferroviaria = gpd.GeoDataFrame(geometry=[LineString([(0,0), (0,0)])], crs="EPSG:4326")
    return malha_ferroviaria, sedes_municipios

with st.spinner("Carregando bases geográficas de apoio..."):
    malha, sedes = carregar_bases_nacionais()

# --- 3. FUNÇÕES AUXILIARES DE GRAFOS E ATRAÇÃO ---
def extrair_grafo_ferroviario(gdf_ferrovia):
    G = nx.Graph()
    for idx, row in gdf_ferrovia.iterrows():
        geom = row.geometry
        if geom.is_empty: continue
        linhas = [geom] if geom.geom_type == 'LineString' else geom.geoms
        for linha in list(linhas):
            coords = list(linha.coords)
            if len(coords) < 2: continue
            for i in range(len(coords) - 1):
                no_u, no_v = coords[i], coords[i+1]
                distancia_km = ((no_u[0] - no_v[0])**2 + (no_u[1] - no_v[1])**2)**0.5 / 1000
                G.add_edge(no_u, no_v, weight=distancia_km)
    return G

def encontrar_no_mais_proximo(grafo, ponto_cidade):
    nos = list(grafo.nodes)
    if not nos: return (0, 0)
    cx, cy = ponto_cidade.x, ponto_cidade.y
    return min(nos, key=lambda no: (no[0] - cx)**2 + (no[1] - cy)**2)

def carregar_camada_recortada(caminho_parquet, bbox_wgs84):
    if os.path.exists(caminho_parquet):
        try: return gpd.read_parquet(caminho_parquet, bbox=bbox_wgs84)
        except Exception: return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
    return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")

# --- 4. INTERFACE DO USUÁRIO (SIDEBAR) ---
st.sidebar.header("1. Seleção de Região")
lista_ufs = sorted(sedes['abbrev_state'].unique())
uf_selecionada = st.sidebar.selectbox("Selecione a UF:", lista_ufs, index=lista_ufs.index("SP") if "SP" in lista_ufs else 0)

sedes_filtradas = sedes[sedes['abbrev_state'] == uf_selecionada].sort_values(by="name_muni")
lista_municipios = sedes_filtradas['name_muni'].unique()

st.sidebar.header("2. Rota da Viagem")
muni_origem = st.sidebar.selectbox("Município de Partida:", lista_municipios)
muni_destino = st.sidebar.selectbox("Município de Destino:", [m for m in lista_municipios if m != muni_origem])

st.sidebar.header("3. Cronograma")
num_trechos = st.sidebar.number_input("Quantidade de trechos a dividir:", min_value=1, value=5)

# --- NOVO: SEÇÃO DE PESOS DA ANÁLISE MULTICRITÉRIO ---
st.sidebar.header("⚙️ 4. Pesos de Criticidade (1 a 5)")
st.sidebar.markdown("<small>Ajuste a importância de cada fator para o cálculo do Score final.</small>", unsafe_allow_html=True)

w_ti = st.sidebar.slider("🏹 Terras Indígenas", 1, 5, value=5, help="Peso para restrições e comunidades tradicionais.")
w_risco = st.sidebar.slider("⚠️ Riscos Geológicos", 1, 5, value=4, help="Peso para áreas de deslizamento e processos erosivos (CPRM).")
w_uc = st.sidebar.slider("🌳 Unidades de Conservação", 1, 5, value=4, help="Peso para restrições de áreas protegidas de todas as esferas.")
w_setores = st.sidebar.slider("👥 Adensamento / Censo", 1, 5, value=2, help="Peso para proximidade a aglomerados urbanos e vulnerabilidade.")
w_rios = st.sidebar.slider("💧 Hidrografia / Rios", 1, 5, value=2, help="Peso para a proximidade de corpos d'água principais.")


# --- 5. MOTOR DE CÁLCULO E ANÁLISE MULTICRITÉRIO ---
if st.sidebar.button("Calcular Rota e Priorizar Trechos", use_container_width=True):
    if len(malha) == 1 and malha.geometry.iloc[0].coords[0] == (0,0):
        st.error("A base ferroviária está ausente.")
    else:
        with st.spinner("Executando cruzamentos geográficos e ponderação de pesos..."):
            malha_m = malha.to_crs(epsg=5880)
            sedes_m = sedes_filtradas.to_crs(epsg=5880)
            
            ponto_origem = sedes_m[sedes_m['name_muni'] == muni_origem].geometry.values[0]
            ponto_destino = sedes_m[sedes_m['name_muni'] == muni_destino].geometry.values[0]
            
            G = extrair_grafo_ferroviario(malha_m)
            no_origem = encontrar_no_mais_proximo(G, ponto_origem)
            no_destino = encontrar_no_mais_proximo(G, ponto_destino)
            
            if no_origem == no_destino:
                st.session_state.dados_calculados = {"erro": "Origem e destino atraídos para o mesmo nó técnico."}
            else:
                try:
                    caminho_nos = nx.shortest_path(G, source=no_origem, target=no_destino, weight='weight')
                    rota_unificada = LineString(caminho_nos)
                    comprimento_total_km = sum(G[caminho_nos[i]][caminho_nos[i+1]]['weight'] for i in range(len(caminho_nos)-1))
                    
                    # Extração espacial: Captura os limites da rota em WGS84
                    gdf_rota_temp = gpd.GeoDataFrame(geometry=[rota_unificada], crs="EPSG:5880").to_crs(epsg=4326)
                    bbox_rota = gdf_rota_temp.geometry.iloc[0].bounds
                    margin = 0.08 # Margem de folga geográfica (~8km)
                    
                    # CORREÇÃO: bbox_expandida agora é uma tupla de 4 floats, não um objeto box()
                    bbox_expandida = (
                        bbox_rota[0] - margin, # minx
                        bbox_rota[1] - margin, # miny
                        bbox_rota[2] + margin, # maxx
                        bbox_rota[3] + margin  # maxy
                    )
                    
                    # Carregamento cirúrgico e direcionado usando a tupla corrigida
                    ucs = carregar_camada_recortada("dados/unidades_conservacao.parquet", bbox_expandida)
                    tis = carregar_camada_recortada("dados/terras_indigenas.parquet", bbox_expandida)
                    riscos = carregar_camada_recortada("dados/areas_risco.parquet", bbox_expandida)
                    rios = carregar_camada_recortada("dados/hidrografia.parquet", bbox_expandida)
                    setores = carregar_camada_recortada("dados/setores_sp.parquet", bbox_expandida)
                    
                    tam_trecho_metros = rota_unificada.length / num_trechos
                    listagem_trechos_diarios = []
                    
                    for i in range(num_trechos):
                        inicio_m = i * tam_trecho_metros
                        fim_m = (i + 1) * tam_trecho_metros
                        sub_trecho_geom = substring(rota_unificada, inicio_m, fim_m)
                        
                        gdf_seg_m = gpd.GeoDataFrame(geometry=[sub_trecho_geom], crs="EPSG:5880")
                        buffer_wgs = gdf_seg_m.buffer(200).to_crs(epsg=4326).iloc[0]
                        
                        # Captura de intersecções reais com as camadas recortadas
                        hit_ucs = ucs[ucs.intersects(buffer_wgs)]['nome_uc'].unique().tolist() if not ucs.empty else []
                        hit_tis = tis[tis.intersects(buffer_wgs)]['nome_ti'].unique().tolist() if not tis.empty else []
                        hit_riscos = riscos[riscos.intersects(buffer_wgs)]['classe_risco'].unique().tolist() if not riscos.empty else []
                        hit_rios = rios[rios.intersects(buffer_wgs)]['nome_rio'].unique().tolist() if not rios.empty else []
                        count_setores = len(setores[setores.intersects(buffer_wgs)]) if not setores.empty else 0
                        
                        # --- MATRIZ MULTICRITÉRIO (Notas de 0 a 10) ---
                        nota_ti = 10.0 if len(hit_tis) > 0 else 0.0
                        nota_uc = 8.0 if len(hit_ucs) > 0 else 0.0
                        nota_rio = 5.0 if len(hit_rios) > 0 else 0.0
                        
                        if any("MUITO ALTO" in r for r in hit_riscos): nota_risco = 10.0
                        elif any("ALTO" in r for r in hit_riscos): nota_risco = 6.0
                        else: nota_risco = 0.0
                            
                        if count_setores > 15: nota_setor = 8.0
                        elif count_setores > 5: nota_setor = 4.0
                        else: nota_setor = 0.0
                        
                        # Cálculo ponderado escalonado pelos Sliders da interface
                        soma_pesos = w_ti + w_risco + w_uc + w_setores + w_rios
                        score_final = (
                            (nota_ti * w_ti) + 
                            (nota_risco * w_risco) + 
                            (nota_uc * w_uc) + 
                            (nota_setor * w_setores) + 
                            (nota_rio * w_rios)
                        ) / soma_pesos
                        
                        # Classificação fina dos envelopes de risco
                        if score_final >= 4.5: criticidade, cor = "CRÍTICA", "red"
                        elif score_final >= 2.5: criticidade, cor = "ALTA", "orange"
                        elif score_final >= 0.8: criticidade, cor = "MÉDIA", "yellow"
                        else: criticidade, cor = "BAIXA", "blue"
                            
                        listagem_trechos_diarios.append({
                            'id_dia': f"Dia {i+1}",
                            'km_inicial': inicio_m / 1000,
                            'km_final': fim_m / 1000,
                            'extensao': sub_trecho_geom.length / 1000,
                            'criticidade': criticidade,
                            'score_num': score_final,
                            'cor_rgb': cor,
                            'interf_uc': ", ".join(hit_ucs) if hit_ucs else "Nenhuma",
                            'interf_ti': ", ".join(hit_tis) if hit_tis else "Nenhuma",
                            'interf_risco': ", ".join(hit_riscos) if hit_riscos else "Nenhum mapeado",
                            'interf_rios': ", ".join(hit_rios) if hit_rios else "Nenhum grande rio",
                            'interf_setores': f"{count_setores} setores urbanos cruzados",
                            'geometry': sub_trecho_geom
                        })
                        
                    gdf_cronograma = gpd.GeoDataFrame(listagem_trechos_diarios, crs="EPSG:5880")
                    gdf_cronograma_wgs84 = gdf_cronograma.to_crs(epsg=4326)
                    
                    st.session_state.dados_calculados = {
                        "muni_origem": muni_origem,
                        "muni_destino": muni_destino,
                        "uf_selecionada": uf_selecionada,
                        "comprimento_total_km": comprimento_total_km,
                        "num_trechos": num_trechos,
                        "gdf_cronograma_wgs84": gdf_cronograma_wgs84,
                        "nos_gerados": len(G.nodes)
                    }
                except nx.NetworkXNoPath:
                    st.session_state.dados_calculados = {"erro": f"Sem conexão ferroviária contínua entre {muni_origem} e {muni_destino}."}
                except Exception as e:
                    st.session_state.dados_calculados = {"erro": f"Erro no processamento espacial: {e}"}

# --- 6. EXIBIÇÃO EM PAINEL INTELIGENTE ---
if st.session_state.dados_calculados is not None:
    dados = st.session_state.dados_calculados
    if "erro" in dados:
        st.error(dados["erro"])
    else:
        st.subheader(f"📍 Rota Priorizada: {dados['muni_origem']} ➡️ {dados['muni_destino']} ({dados['uf_selecionada']})")
        st.success("Análise de criticidade baseada na ponderação de pesos atual recalculada!")
        
        col1, col2 = st.columns(2)
        col1.metric("Distância Total nos Trilhos", f"{dados['comprimento_total_km']:.2f} km")
        col2.metric("Média de Deslocamento Diário", f"{(dados['comprimento_total_km'] / dados['num_trechos']):.2f} km/dia")
        
        st.write("---")
        col_lista, col_mapa = st.columns([4, 5])
        
        with col_lista:
            st.write("### 🗓️ Matriz de Sensibilidade de Campo")
            gdf_wgs84 = dados['gdf_cronograma_wgs84']
            
            for idx, row in gdf_wgs84.iterrows():
                texto_trecho = f"**{row['id_dia']}:** km {row['km_inicial']:.1f} ao {row['km_final']:.1f} ({row['extensao']:.1f} km) — **Score: {row['score_num']:.2f}**"
                
                if row['criticidade'] == "CRÍTICA": st.error(f"🔴 {texto_trecho} — **CRÍTICO**")
                elif row['criticidade'] == "ALTA": st.warning(f"🟠 {texto_trecho} — **SENSÍVEL (ALTO)**")
                elif row['criticidade'] == "MÉDIA": st.info(f"🟡 {texto_trecho} — **MODERADO (MÉDIO)**")
                else: st.success(f"🔵 {texto_trecho} — **BAIXO IMPACTO**")
                
                with st.expander("Ver Intersecções Detectadas"):
                    st.write(f"⚠️ **Riscos Geológicos (CPRM):** {row['interf_risco']}")
                    st.write(f"🌳 **Unidades de Conservação:** {row['interf_uc']}")
                    st.write(f"🏹 **Terras Indígenas (Funai):** {row['interf_ti']}")
                    st.write(f"💧 **Corpos d'Água Principais:** {row['interf_rios']}")
                    st.write(f"👥 **Malha Censitária (IBGE):** {row['interf_setores']}")
                st.write("")
        
        with col_mapa:
            st.write("### 🗺️ Mapa Temático Dinâmico")
            centro_mapa = gdf_wgs84.unary_union.centroid
            m = folium.Map(location=[centro_mapa.y, centro_mapa.x], zoom_start=8, tiles="CartoDB positron")
            
            for idx, row in gdf_wgs84.iterrows():
                cor = row['cor_rgb']
                geo_json_features = folium.GeoJson(
                    row['geometry'].__geo_interface__,
                    style_function=lambda x, c=cor: {'color': c, 'weight': 6, 'opacity': 0.9}
                )
                
                popup_html = f"""
                <div style='font-family: Arial, sans-serif; width: 230px; font-size:12px;'>
                    <h4 style='margin:0 0 5px 0; color:{cor};'>{row['id_dia']} ({row['criticidade']})</h4>
                    <b>Score de Risco:</b> {row['score_num']:.2f}<br>
                    <b>Trecho:</b> km {row['km_inicial']:.1f} ao {row['km_final']:.1f}<br>
                    <b>Risco CPRM:</b> {row['interf_risco']}<br>
                    <b>UCs:</b> {row['interf_uc']}<br>
                    <b>TIs:</b> {row['interf_ti']}<br>
                    <b>Rios:</b> {row['interf_rios']}<br>
                    <b>Censo IBGE:</b> {row['interf_setores']}
                </div>
                """
                folium.Popup(popup_html, max_width=250).add_to(geo_json_features)
                geo_json_features.add_to(m)
                
            st_folium(m, height=550, use_container_width=True)
