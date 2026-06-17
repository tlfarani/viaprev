import streamlit as st
import geopandas as gpd
import geobr
import networkx as nx
import folium
from streamlit_folium import st_folium
from shapely.ops import substring
from shapely.geometry import LineString, Point

# Configuração da página do Streamlit
st.set_page_config(
    layout="wide", 
    page_title="Planejador Nacional de Vistoria Ferroviária",
    page_icon="🚊"
)

st.title("🚊 Planejador Nacional de Vistoria Ferroviária (Rede/Grafos)")
st.markdown("Ferramenta otimizada para traçado de rotas sobre trilhos e divisão de trechos operacionais diários.")

# --- 1. CARREGAMENTO DOS DADOS NACIONAIS ---
@st.cache_data(show_spinner=False)
def carregar_bases_nacionais():
    """
    Carrega as sedes dos municípios via geobr e a malha ferroviária em formato GeoParquet.
    """
    sedes_municipios = geobr.read_municipal_seat()
    
    try:
        malha_ferroviaria = gpd.read_parquet("dados/malha_ferroviaria.parquet")
        if malha_ferroviaria.crs is None:
            malha_ferroviaria.set_crs(epsg=4326, inplace=True)
    except Exception:
        st.sidebar.error("❌ Arquivo 'dados/malha_ferroviaria.parquet' não encontrado no repositório!")
        malha_ferroviaria = gpd.GeoDataFrame(geometry=[LineString([(0,0), (0,0)])], crs="EPSG:4326")
        
    return malha_ferroviaria, sedes_municipios

with st.spinner("Carregando bases geográficas nacionais..."):
    malha, sedes = carregar_bases_nacionais()


# --- 2. FUNÇÕES AUXILIARES DE ALTA PERFORMANCE (MATEMÁTICA PURA) ---
def extrair_grafo_ferroviario(gdf_ferrovia):
    """
    Transforma as linhas em Grafo usando matemática pura (Pitágoras).
    Evita a criação de objetos Shapely dentro do loop, rodando instantaneamente.
    """
    G = nx.Graph()
    
    for idx, row in gdf_ferrovia.iterrows():
        geom = row.geometry
        if geom.is_empty:
            continue
        if geom.geom_type == 'LineString':
            linhas = [geom]
        elif geom.geom_type == 'MultiLineString':
            linhas = geom.geoms
        else:
            continue
            
        for linha in list(linhas):
            coords = list(linha.coords)
            if len(coords) < 2:
                continue
            
            # Varre os vértices usando estruturas nativas numéricas do Python
            for i in range(len(coords) - 1):
                no_u = coords[i]
                no_v = coords[i+1]
                
                # Geometria projetada em metros: Pitágoras puro para cálculo de distância
                distancia_km = ((no_u[0] - no_v[0])**2 + (no_u[1] - no_v[1])**2)**0.5 / 1000
                
                G.add_edge(no_u, no_v, weight=distancia_km)
                
    return G

def encontrar_no_mais_proximo(grafo, ponto_cidade):
    """
    Encontra o nó ferroviário (x, y) mais próximo usando busca matemática otimizada.
    """
    nos = list(grafo.nodes)
    if not nos:
        return (0, 0)
    
    cx, cy = ponto_cidade.x, ponto_cidade.y
    # Encontra o par ordenado que minimiza a distância euclidiana ao quadrado
    no_proximo = min(nos, key=lambda no: (no[0] - cx)**2 + (no[1] - cy)**2)
    return no_proximo


# --- 3. INTERFACE DO USUÁRIO (SIDEBAR) ---
st.sidebar.header("1. Seleção de Região")

lista_ufs = sorted(sedes['abbrev_state'].unique())
uf_selecionada = st.sidebar.selectbox(
    "Selecione a UF de atuação:", 
    lista_ufs, 
    index=lista_ufs.index("SP") if "SP" in lista_ufs else 0
)

sedes_filtradas = sedes[sedes['abbrev_state'] == uf_selecionada].sort_values(by="name_muni")
lista_municipios = sedes_filtradas['name_muni'].unique()

st.sidebar.header("2. Rota da Viagem")
muni_origem = st.sidebar.selectbox("Município de Partida:", lista_municipios)
muni_destino = st.sidebar.selectbox("Município de Destino:", [m for m in lista_municipios if m != muni_origem])

st.sidebar.header("3. Cronograma")
datas = st.sidebar.date_input("Período da Vistoria:", [])

if len(datas) == 2:
    data_ini, data_fim = datas
    dias_trabalho = (data_fim - data_ini).days + 1
    num_trechos = st.sidebar.number_input(
        "Quantidade de trechos a dividir:", 
        min_value=1, 
        value=dias_trabalho, 
        help="Por padrão, adota-se 1 trecho por dia de trabalho."
    )
else:
    num_trechos = st.sidebar.number_input("Quantidade de trechos a dividir:", min_value=1, value=5)
    st.sidebar.warning("Selecione a data de início e término para sincronizar com os dias de trabalho.")


# --- 4. PROCESSAMENTO DA ROTA E CRONOGRAMA DIÁRIO ---
if st.sidebar.button("Calcular Rota e Dividir Trechos", use_container_width=True):
    if len(malha) == 1 and malha.geometry.iloc[0].coords[0] == (0,0):
        st.error("A base de dados ferroviária real está ausente ou vazia.")
    else:
        st.subheader(f"📍 Planejamento Estruturado: {muni_origem} ➡️ {muni_destino} ({uf_selecionada})")
        
        with st.spinner("Reprojetando coordenadas para cálculo métrico..."):
            malha_m = malha.to_crs(epsg=5880)
            sedes_m = sedes_filtradas.to_crs(epsg=5880)
        
        ponto_origem = sedes_m[sedes_m['name_muni'] == muni_origem].geometry.values[0]
        ponto_destino = sedes_m[sedes_m['name_muni'] == muni_destino].geometry.values[0]
        
        with st.spinner("Construindo rede lógica de grafos da malha... (Modo Ultra Rápido)"):
            G = extrair_grafo_ferroviario(malha_m)
            no_origem = encontrar_no_mais_proximo(G, ponto_origem)
            no_destino = encontrar_no_mais_proximo(G, ponto_destino)
            
        # Expander de Diagnóstico Técnico leve
        with st.expander("🔍 Detalhes Técnicos de Atração (Snapping)"):
            st.write(f"**Nós gerados na malha:** {len(G.nodes)}")
            st.write(f"**Nó mais próximo da Origem:** ({no_origem[0]:.1f}, {no_origem[1]:.1f})")
            st.write(f"**Nó mais próximo do Destino:** ({no_destino[0]:.1f}, {no_destino[1]:.1f})")
            
        if no_origem == no_destino:
            st.error(
                f"⚠️ **Erro de Escala/Topologia:** O algoritmo mapeou a origem ({muni_origem}) e o destino ({muni_destino}) para o mesmo ponto físico da ferrovia.\n\n"
                f"**Como resolver?** Certifique-se de que o arquivo original convertido para `.parquet` possuía um sistema de coordenadas geográficas válido (como WGS84 - EPSG:4326) antes da conversão."
            )
        else:
            try:
                # Calcula o caminho mínimo de nós sobre o grafo
                caminho_nos = nx.shortest_path(G, source=no_origem, target=no_destino, weight='weight')
                
                # Como os nós são as próprias coordenadas (x,y), a rota é gerada de forma direta e ordenada
                rota_unificada = LineString(caminho_nos)
                
                # Calcula o comprimento total somando os pesos das arestas do caminho
                comprimento_total_km = sum(G[caminho_nos[i]][caminho_nos[i+1]]['weight'] for i in range(len(caminho_nos)-1))
                
                st.success("Rota real mapeada com sucesso sobre os trilhos!")
                
                col1, col2 = st.columns(2)
                col1.metric("Distância Total nos Trilhos", f"{comprimento_total_km:.2f} km")
                col2.metric("Média Diária de Vistoria", f"{(comprimento_total_km / num_trechos):.2f} km/dia")
                
                # --- 5. FATIAMENTO GEOMÉTRICO E COLETA DE DADOS ---
                comprimento_total_metros = rota_unificada.length
                tam_trecho_metros = comprimento_total_metros / num_trechos
                
                listagem_trechos_diarios = []
                
                for i in range(num_trechos):
                    inicio_m = i * tam_trecho_metros
                    fim_m = (i + 1) * tam_trecho_metros
                    
                    sub_trecho_geom = substring(rota_unificada, inicio_m, fim_m)
                    
                    km_inicial = inicio_m / 1000
                    km_final = fim_m / 1000
                    extensao_dia = (fim_m - inicio_m) / 1000
                    
                    listagem_trechos_diarios.append({
                        'id_dia': f"Dia {i+1}",
                        'km_inicial': km_inicial,
                        'km_final': km_final,
                        'extensao': extensao_dia,
                        'geometry': sub_trecho_geom
                    })
                    
                gdf_cronograma = gpd.GeoDataFrame(listagem_trechos_diarios, crs="EPSG:5880")
                gdf_cronograma_wgs84 = gpd.GeoDataFrame(gdf_cronograma, geometry=gdf_cronograma.geometry).to_crs(epsg=4326)
                
                # --- 6. CRIAÇÃO E EXIBIÇÃO DO MAPA INTERATIVO ---
                st.write("---")
                col_mapa, col_lista = st.columns([1, 2])
                
                with col_mapa:
                    st.write(f"### 🗓️ Resumo Operacional")
                    for idx, row in gdf_cronograma.iterrows():
                        st.write(
                            f"• **{row['id_dia']}:** km {row['km_inicial']:.1f} ao km {row['km_final']:.1f} "
                            f"(`{row['extensao']:.1f} km`)"
                        )
                
                with col_lista:
                    st.write("### 🗺️ Visualização Espacial dos Trechos")
                    centro_mapa = gdf_cronograma_wgs84.unary_union.centroid
                    
                    m = folium.Map(
                        location=[centro_mapa.y, centro_mapa.x], 
                        zoom_start=8, 
                        tiles="OpenStreetMap"
                    )
                    
                    cores_paleta = ['blue', 'green', 'red', 'purple', 'orange', 'darkred', 'cadetblue', 'darkpurple']
                    
                    for idx, row in gdf_cronograma_wgs84.iterrows():
                        cor_trecho = cores_paleta[idx % len(cores_paleta)]
                        
                        geo_json_features = folium.GeoJson(
                            row['geometry'].__geo_interface__,
                            style_function=lambda x, cor=cor_trecho: {
                                'color': cor,
                                'weight': 6,
                                'opacity': 0.85
                            }
                        )
                        
                        popup_html = f"""
                        <div style='font-family: Arial, sans-serif; width: 160px;'>
                            <h4 style='margin:0 0 5px 0; color:{cor_trecho};'>{row['id_dia']}</h4>
                            <b>Início:</b> km {row['km_inicial']:.1f}<br>
                            <b>Fim:</b> km {row['km_final']:.1f}<br>
                            <b>Extensão:</b> {row['extensao']:.1f} km
                        </div>
                        """
                        folium.Popup(popup_html, max_width=200).add_to(geo_json_features)
                        geo_json_features.add_to(m)
                        
                    st_folium(m, height=500, use_container_width=True)
                    
            except nx.NetworkXNoPath:
                st.error(f"❌ Não foi encontrada uma conexão ferroviária contínua na base de dados entre **{muni_origem}** e **{muni_destino}**.")
            except Exception as e:
                st.error(f"Erro inesperado durante o processamento: {e}")
