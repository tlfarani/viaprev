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
st.markdown("Análise multicritério interestadual com mapeamento de Pontes, Passagens de Nível (PN) e Pátios.")

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

def carregar_camada_com_telemetria(caminho_parquet, bbox_wgs84, nome_camada):
    """Carrega dados geográficos com validação contra falsos zeros e logs de execução."""
    log = {"camada": nome_camada, "status": "Não executado", "registros": 0, "detalhes": ""}
    if not os.path.exists(caminho_parquet):
        log["status"] = "⚠️ Arquivo opcional ausente"
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326"), log
    try:
        gdf = gpd.read_parquet(caminho_parquet, bbox=bbox_wgs84)
        gdf = gdf.to_crs(epsg=4326) if gdf.crs is not None else gdf.set_crs(epsg=4326)
        log["status"] = "🟢 Sucesso (BBox Nativo)"
        log["registros"] = len(gdf)
        if len(gdf) == 0:
            log["status"] = "干 Acionado Fallback"
            gdf_completo = gpd.read_parquet(caminho_parquet)
            gdf_completo = gdf_completo.to_crs(epsg=4326) if gdf_completo.crs is not None else gdf_completo.set_crs(epsg=4326)
            area_busca = box(*bbox_wgs84)
            gdf = gdf_completo[gdf_completo.intersects(area_busca)].copy()
            log["registros"] = len(gdf)
        return gdf, log
    except Exception:
        try:
            gdf_completo = gpd.read_parquet(caminho_parquet)
            gdf_completo = gdf_completo.to_crs(epsg=4326) if gdf_completo.crs is not None else gdf_completo.set_crs(epsg=4326)
            area_busca = box(*bbox_wgs84)
            gdf = gdf_completo[gdf_completo.intersects(area_busca)].copy()
            log["registros"] = len(gdf)
            log["status"] = "🟢 Sucesso (Mapeamento RAM)"
            return gdf, log
        except Exception as e:
            log["status"] = "🔴 Falha Crítica"
            return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326"), log


# --- 4. INTERFACE DO USUÁRIO (SIDEBAR INTERESTADUAL BLINDADA) ---
st.sidebar.header("1. Origem e Destino (Interestadual)")
lista_ufs = sorted(sedes['abbrev_state'].unique())

uf_origem = st.sidebar.selectbox("UF de Partida:", lista_ufs, index=lista_ufs.index("SP") if "SP" in lista_ufs else 0)
sedes_origem_df = sedes[sedes['abbrev_state'] == uf_origem].sort_values(by="name_muni")
muni_origem = st.sidebar.selectbox("Município de Partida:", sedes_origem_df['name_muni'].unique(), index=0)

uf_destino = st.sidebar.selectbox("UF de Destino:", lista_ufs, index=lista_ufs.index("SP") if "SP" in lista_ufs else 0)
sedes_destino_df = sedes[sedes['abbrev_state'] == uf_destino].sort_values(by="name_muni")
muni_destino = st.sidebar.selectbox("Município de Destino:", sedes_destino_df['name_muni'].unique(), index=min(1, len(sedes_destino_df)-1))

st.sidebar.header("2.1. Controle de Concessionárias")
if 'concessionaria' in malha.columns:
    col_concess_alvo = 'concessionaria'
    lista_concessionarias = sorted(malha[col_concess_alvo].unique())
    default_selecao = [c for c in lista_concessionarias if "PAULISTA" in c or "MRS" in c or "CENTRO" in c]
else:
    col_concess_alvo = None
    lista_concessionarias = []
    default_selecao = []

if col_concess_alvo:
    concessionarias_selecionadas = st.sidebar.multiselect(
        "Ferrovias autorizadas para o traçado:", options=lista_concessionarias, default=default_selecao
    )
else:
    concessionarias_selecionadas = None

st.sidebar.header("3. Cronograma")
num_trechos = st.sidebar.number_input("Quantidade de trechos a dividir:", min_value=1, value=3)

st.sidebar.header("⚙️ 4. Pesos de Criticidade (1 a 5)")
w_ti = st.sidebar.slider("🏹 Terras Indígenas", 1, 5, value=5)
w_risco = st.sidebar.slider("⚠️ Riscos Geológicos", 1, 5, value=4)
w_uc = st.sidebar.slider("🌳 Unidades de Conservação", 1, 5, value=4)
w_setores = st.sidebar.slider("👥 Adensamento / Censo", 1, 5, value=2)
w_rios = st.sidebar.slider("💧 Hidrografia / Rios", 1, 5, value=2)


# --- 5. MOTOR DE CÁLCULO, INTERSECÇÕES E ANÁLISE MULTICRITÉRIO ---
if st.sidebar.button("Calcular Rota e Priorizar Trechos", use_container_width=True):
    if len(malha) == 1 and malha.geometry.iloc[0].coords[0] == (0,0):
        st.error("A base ferroviária está ausente.")
    else:
        with st.spinner("Traçando rota interestadual e calculando cruzamentos estruturais..."):
            
            malha_filtrada = malha.copy()
            if concessionarias_selecionadas and col_concess_alvo:
                malha_filtrada = malha_filtrada[malha_filtrada[col_concess_alvo].isin(concessionarias_selecionadas)]
                
            malha_m = malha_filtrada.to_crs(epsg=5880)
            sedes_origem_m = sedes_origem_df.to_crs(epsg=5880)
            sedes_destino_m = sedes_destino_df.to_crs(epsg=5880)
            
            ponto_origem = sedes_origem_m[sedes_origem_m['name_muni'] == muni_origem].geometry.values[0]
            ponto_destino = sedes_destino_m[sedes_destino_m['name_muni'] == muni_destino].geometry.values[0]
            
            G = extrair_grafo_ferroviario(malha_m)
            no_origem = encontrar_no_mais_proximo(G, ponto_origem)
            no_destino = encontrar_no_mais_proximo(G, ponto_destino)
            
            if no_origem == no_destino:
                st.error("Origem e destino atraídos para o mesmo nó técnico.")
            else:
                try:
                    caminho_nos = nx.shortest_path(G, source=no_origem, target=no_destino, weight='weight')
                    rota_unificada = LineString(caminho_nos)
                    comprimento_total_km = sum(G[caminho_nos[i]][caminho_nos[i+1]]['weight'] for i in range(len(caminho_nos)-1))
                    
                    gdf_rota_temp = gpd.GeoDataFrame(geometry=[rota_unificada], crs="EPSG:5880").to_crs(epsg=4326)
                    bbox_rota = gdf_rota_temp.geometry.iloc[0].bounds
                    margin = 0.08
                    bbox_expandida = (bbox_rota[0]-margin, bbox_rota[1]-margin, bbox_rota[2]+margin, bbox_rota[3]+margin)
                    
                    # CARREGAMENTO COMPLETO DA MATRIZ DE DADOS SENSÍVEIS E LOGÍSTICOS
                    ucs, log_uc = carregar_camada_com_telemetria("dados/unidades_conservacao.parquet", bbox_expandida, "Unidades de Conservação")
                    tis, log_ti = carregar_camada_com_telemetria("dados/terras_indigenas.parquet", bbox_expandida, "Terras Indígenas")
                    riscos, log_risco = carregar_camada_com_telemetria("dados/areas_risco.parquet", bbox_expandida, "Áreas de Risco (CPRM)")
                    rios, log_rio = carregar_camada_com_telemetria("dados/hidrografia.parquet", bbox_expandida, "Hidrografia (Rios)")
                    setores, log_setor = carregar_camada_com_telemetria("dados/setores_sp.parquet", bbox_expandida, "Setores Censitários (IBGE)")
                    rodovias, log_rod = carregar_camada_com_telemetria("dados/rodovias.parquet", bbox_expandida, "Malha Rodoviária")
                    patios, log_pat = carregar_camada_com_telemetria("dados/patios_oficinas.parquet", bbox_expandida, "Pátios e Oficinas")
                    
                    painel_logs = [log_uc, log_ti, log_risco, log_rio, log_setor, log_rod, log_pat]
                    
                    tam_trecho_metros = rota_unificada.length / num_trechos
                    listagem_trechos_diarios = []
                    
                    for i in range(num_trechos):
                        inicio_m = i * tam_trecho_metros
                        fim_m = (i + 1) * tam_trecho_metros
                        sub_trecho_geom = substring(rota_unificada, inicio_m, fim_m)
                        
                        gdf_seg_m = gpd.GeoDataFrame(geometry=[sub_trecho_geom], crs="EPSG:5880")
                        sub_trecho_wgs = gdf_seg_m.to_crs(epsg=4326).geometry.iloc[0]
                        buffer_wgs = gdf_seg_m.buffer(200).to_crs(epsg=4326).iloc[0]
                        
                        # Cruzamentos Ambientais Standard
                        hit_ucs = ucs[ucs.intersects(buffer_wgs)]['nome_uc'].unique().tolist() if not ucs.empty else []
                        hit_tis = tis[tis.intersects(buffer_wgs)]['nome_ti'].unique().tolist() if not tis.empty else []
                        hit_riscos = riscos[riscos.intersects(buffer_wgs)]['classe_risco'].unique().tolist() if not riscos.empty else []
                        hit_rios = rios[rios.intersects(buffer_wgs)]['nome_rio'].unique().tolist() if not rios.empty else []
                        count_setores = len(setores[setores.intersects(buffer_wgs)]) if not setores.empty else 0
                        
                        # Cruzamento Logístico: Pátios e Oficinas na faixa de domínio
                        hit_patios = patios[patios.intersects(buffer_wgs)] if not patios.empty else gpd.GeoDataFrame()
                        col_nome_patio = [c for c in hit_patios.columns if 'nome' in c or 'patio' in c or 'oficina' in c]
                        nomes_patios = hit_patios[col_nome_patio[0]].unique().tolist() if (not hit_patios.empty and col_nome_patio) else []
                        
                        # --- EXTRATOR MATEMÁTICO DE PONTOS DE INTERSECÇÃO (PONTES E PNs) ---
                        list_pn_coords = []
                        if not rodovias.empty:
                            rod_hits = rodovias[rodovias.intersects(sub_trecho_wgs)]
                            if not rod_hits.empty:
                                inter_geom = rod_hits.intersection(sub_trecho_wgs)
                                for g in inter_geom:
                                    if g.geom_type == 'Point': list_pn_coords.append((g.y, g.x))
                                    elif g.geom_type == 'MultiPoint': list_pn_coords.extend([(p.y, p.x) for p in g.geoms])
                                    
                        list_pontes_coords = []
                        if not rios.empty:
                            rio_hits = rios[rios.intersects(sub_trecho_wgs)]
                            if not rio_hits.empty:
                                inter_rio_geom = rio_hits.intersection(sub_trecho_wgs)
                                for g in inter_rio_geom:
                                    if g.geom_type == 'Point': list_pontes_coords.append((g.y, g.x))
                                    elif g.geom_type == 'MultiPoint': list_pontes_coords.extend([(p.y, p.x) for p in g.geoms])
                        
                        # --- MATRIZ MULTICRITÉRIO DO SCORE ---
                        nota_ti = 10.0 if len(hit_tis) > 0 else 0.0
                        nota_uc = 8.0 if len(hit_ucs) > 0 else 0.0
                        nota_rio = 5.0 if len(hit_rios) > 0 else 0.0
                        nota_risco = 10.0 if any("MUITO ALTO" in r for r in hit_riscos) else (6.0 if any("ALTO" in r for r in hit_riscos) else 0.0)
                        nota_setor = 8.0 if count_setores > 25 else (4.0 if count_setores > 8 else 0.0)
                        
                        soma_pesos = w_ti + w_risco + w_uc + w_setores + w_rios
                        score_final = ((nota_ti * w_ti) + (nota_risco * w_risco) + (nota_uc * w_uc) + (nota_setor * w_setores) + (nota_rio * w_rios)) / soma_pesos
                        
                        criticidade, cor = ("CRÍTICA", "red") if score_final >= 4.5 else (("ALTA", "orange") if score_final >= 2.5 else (("MÉDIA", "yellow") if score_final >= 0.8 else ("BAIXA", "blue")))
                        
                        listagem_trechos_diarios.append({
                            'id_dia': f"Dia {i+1}",
                            'km_inicial': inicio_m / 1000,
                            'km_final': fim_m / 1000,
                            'extensao': sub_trecho_geom.length / 1000,
                            'criticidade': criticidade, 'score_num': score_final, 'cor_rgb': cor,
                            'interf_uc': ", ".join(hit_ucs) if hit_ucs else "Nenhuma",
                            'interf_ti': ", ".join(hit_tis) if hit_tis else "Nenhuma",
                            'interf_risco': ", ".join(hit_riscos) if hit_riscos else "Nenhum mapeado",
                            'interf_rios': ", ".join(hit_rios) if hit_rios else "Nenhum grande rio",
                            'interf_setores': f"{count_setores} setores urbanos cruzados",
                            'interf_patios': ", ".join(nomes_patios) if nomes_patios else "Nenhum pátio na faixa de domínio",
                            'pn_pontos': list_pn_coords, 'pontes_pontes': list_pontes_coords,
                            'geometry': sub_trecho_geom
                        })
                        
                    gdf_cronograma = gpd.GeoDataFrame(listagem_trechos_diarios, crs="EPSG:5880")
                    gdf_cronograma_wgs84 = gdf_cronograma.to_crs(epsg=4326)
                    
                    st.session_state.dados_calculados = {
                        "muni_origem": muni_origem, "muni_destino": muni_destino,
                        "uf_origem": uf_origem, "uf_destino": uf_destino,
                        "comprimento_total_km": comprimento_total_km, "num_trechos": num_trechos,
                        "gdf_cronograma_wgs84": gdf_cronograma_wgs84, "logs_diagnostico": painel_logs
                    }
                except nx.NetworkXNoPath:
                    st.error("Sem conexão ferroviária contínua instalada entre as duas cidades nas ferrovias autorizadas.")

# --- 6. EXIBIÇÃO EM PAINEL INTELIGENTE ---
if st.session_state.dados_calculados is not None:
    dados = st.session_state.dados_calculados
    if "erro" in dados: st.error(dados["erro"])
    else:
        st.subheader(f"📍 Rota Priorizada: {dados['muni_origem']} ({dados['uf_origem']}) ➡️ {dados['muni_destino']} ({dados['uf_destino']})")
        st.success("Análise multicritério estrutural interestadual calculada com sucesso!")
        
        col1, col2 = st.columns(2)
        col1.metric("Distância Total nos Trilhos", f"{dados['comprimento_total_km']:.2f} km")
        col2.metric("Média de Deslocamento Diário", f"{(dados['comprimento_total_km'] / dados['num_trechos']):.2f} km/dia")
        
        if "logs_diagnostico" in dados:
            with st.expander("🛠️ Painel de Diagnóstico e Validação Geográfica"):
                for log in dados["logs_diagnostico"]:
                    st.markdown(f"**🔹 Camada:** {log['camada']} | **Status:** {log['status']} | **Feições na Rota:** `{log['registros']}`")
        
        st.write("---")
        col_lista, col_mapa = st.columns([4, 5])
        
        with col_lista:
            st.write("### 🗓️ Matriz de Sensibilidade e Logística")
            gdf_wgs84 = dados['gdf_cronograma_wgs84']
            
            for idx, row in gdf_wgs84.iterrows():
                texto_trecho = f"**{row['id_dia']}:** km {row['km_inicial']:.1f} ao {row['km_final']:.1f} ({row['extensao']:.1f} km) — **Score: {row['score_num']:.2f}**"
                if row['criticidade'] == "CRÍTICA": st.error(f"🔴 {texto_trecho}")
                elif row['criticidade'] == "ALTA": st.warning(f"🟠 {texto_trecho}")
                elif row['criticidade'] == "MÉDIA": st.info(f"🟡 {texto_trecho}")
                else: st.success(f"🔵 {texto_trecho}")
                
                with st.expander("Ver Cruzamentos e Estruturas Detectadas"):
                    st.markdown(f"🛣️ **Passagens de Nível (PN Rodovias):** `{len(row['pn_pontos'])}` cruzamentos detectados.")
                    st.markdown(f"🌉 **Pontes Ferroviárias (Rios):** `{len(row['pontes_pontes'])}` cruzamentos sobre corpos d'água.")
                    st.markdown(f"🏢 **Pátios e Infraestrutura:** {row['interf_patios']}")
                    st.write("---")
                    st.caption(f"⚠️ **CPRM:** {row['interf_risco']} | 🌳 **UCs:** {row['interf_uc']} | 👥 **IBGE:** {row['interf_setores']}")
                st.write("")
        
        with col_mapa:
            st.write("### 🗺️ Mapa Temático Dinâmico Avançado")
            centro_mapa = gdf_wgs84.unary_union.centroid
            m = folium.Map(location=[centro_mapa.y, centro_mapa.x], zoom_start=8, tiles="CartoDB positron")
            
            # 1. Desenha os trechos coloridos da ferrovia
            for idx, row in gdf_wgs84.iterrows():
                cor = row['cor_rgb']
                geo_json_features = folium.GeoJson(
                    row['geometry'].__geo_interface__,
                    style_function=lambda x, c=cor: {'color': c, 'weight': 6, 'opacity': 0.9}
                )
                popup_html = f"<b>{row['id_dia']}</b><br>Score: {row['score_num']:.2f}<br>Pontes: {len(row['pontes_pontes'])}<br>PNs: {len(row['pn_pontos'])}"
                folium.Popup(popup_html, max_width=200).add_to(geo_json_features)
                geo_json_features.add_to(m)
                
                # 2. Plotagem dinâmica das Passagens de Nível (Pontos Pretos/Laranjas)
                for pt in row['pn_pontos']:
                    folium.CircleMarker(
                        location=pt, radius=4, color='black', fill=True, fill_color='orange', fill_opacity=1,
                        popup="🛣️ Passagem de Nível (Cruzamento Rodoviário)"
                    ).add_to(m)
                    
                # 3. Plotagem dinâmica das Pontes sobre Rios (Pontos Azuis)
                for pt_rio in row['pontes_pontes']:
                    folium.CircleMarker(
                        location=pt_rio, radius=4, color='darkblue', fill=True, fill_color='cyan', fill_opacity=1,
                        popup="🌉 Ponte Ferroviária (Cruzamento de Rio Principal)"
                    ).add_to(m)
                
            st_folium(m, height=580, use_container_width=True)
