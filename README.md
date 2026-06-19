# 🚊 ViaPrev: Planejador Nacional de Vistoria Ferroviária com Matriz de Risco

Este repositório hospeda um **SAD (Sistema de Apoio à Decisão)** geoespacial e logístico desenvolvido em Python e implantado via Streamlit Cloud. O objetivo principal do aplicativo é automatizar o traçado de rotas ferroviárias contínuas em nível nacional, segmentar o cronograma de deslocamento das equipes e aplicar modelos de **Análise Multicritério (AHP/WLC)** para apontar instantaneamente os trechos de maior vulnerabilidade e sensibilidade socioambiental (*Hotspots*).

---

## 🚀 Funcionalidades Principais

* **Roteirização Multitrecho por Grafos Topológicos:** Conexão matemática precisa através da biblioteca `NetworkX` que une os trilhos federais de ponta a ponta. Calcula o algoritmo de menor caminho (`shortest_path`) de forma sequencial (*Multi-leg routing*), costurando pernas consecutivas sem o risco de duplicação de nós técnicos de emenda.
* **Planejador de Viagem Avançado com Paradas:** Suporta a inclusão dinâmica de até **6 paradas intermediárias obrigatórias** além da origem e do destino. O frontend renderiza marcadores distintos com bandeiras e sinalizações visuais táticas (`play` verde, `flag` azul e `stop` vermelho) para cada ponto estratégico definido pelo auditor.
* **Filtro Comercial por Concessionária (Base PNV):** Permite isolar ou combinar malhas concedidas (ex: Rumo Malha Paulista, MRS Logística, FCA), recalculando o grafo em tempo real e bloqueando trechos operados por empresas restritas na vistoria.
* **Divisão Automatizada de Cronograma (Macro Trechos):** Fatiamento linear preciso da rota unificada final na quantidade de dias ou equipes estipuladas pelo analista de campo.
* **Detector de Hotspots de 1 km (Micro Trechos):** Varredura interna em memória RAM que quebra cada macro trecho em segmentos exatos de 1 km, isolando e listando os **5 pontos mais críticos do dia** com extração de coordenadas nativas (Latitude e Longitude do início e fim do alvo).
* **Mapeamento de Ícones Temáticos de Apoio:** Plotagem dinâmica de pontos logísticos com estilização categórica baseada no FontAwesome. Diferencia visualmente Oficinas de Manutenção (🔧), Terminais de Cargas (🔲) e Pátios Operacionais (🚂) integrando os nomes oficiais recuperados das bases de auditoria.
* **Cruzamento de Precisão Hídrica (BHO/ANA 25m):** Intersecção espacial de alta fidelidade com a Base Hidrográfica Ottocodificada (BHO) da ANA na escala 1:5.000. O motor identifica cruzamentos com corpos d'água e plota a localização geométrica exata de **Pontes Ferroviárias**, operando de forma resiliente contra meandros sinuosos complexos (como os da Serra do Mar).
* **Mesa de Luz para Auditoria (Visual Layer Control):** Painel interativo flutuante no mapa que permite ligar/desligar de forma independente as camadas cartográficas recortadas para validação visual contra o mapa base.

---

## 📐 Premissas Metodológicas e Matriz de Risco

A classificação de criticidade socioambiental do planejador adota o método de **Combinação Linear Ponderada (Análise Multicritério - WLC)**. 

### 1. Faixa de Domínio (Buffer Espacial)
Todas as intersecções de vulnerabilidade são calculadas gerando uma zona de amortecimento (buffer geográfico) de **200 metros** de raio em torno do eixo central dos trilhos. Para clipping e otimização cartográfica de exibição no frontend (evitando Buffer Overflow no navegador), adota-se um corredor tático estrito de **1,5 km**.

### 2. Pesos e Notas Estipulados
O sistema cruza as feições geográficas dentro do buffer atribuindo notas fixas de sensibilidade ($0.0$ a $10.0$) multiplicadas pelos pesos dinâmicos ($1$ a $5$) regulados pelo analista na interface lateral do sistema:

| Critério Socioambiental | Nota Padrão (Se Houver Intersecção) | Peso Padrão | Canal de Origem |
| :--- | :---: | :---: | :--- |
| **🏹 Terras Indígenas (TI)** | $10.0$ | `5` | FUNAI |
| **⚠️ Áreas de Risco Geológico** | $10.0$ (Muito Alto) / $6.0$ (Alto) | `4` | SGB / CPRM |
| **🌳 Unidades de Conservação (UC)** | $8.0$ | `4` | MMA / ICMBio |
| **👥 Adensamento Urbano (Censo)** | $8.0$ ($>25$ setores) / $4.0$ ($>8$ setores) | `2` | IBGE |
| **💧 Hidrografia (ANA BHO)** | $5.0$ | `2` | ANA (Cursos 5k) |

### 3. Equação do Score Final
O cálculo do índice de risco final de cada segmento linear é dado por:

$$Score = \frac{\sum (Nota_i \times Peso_i)}{\sum Peso_i}$$

Os resultados são classificados em 4 faixas rigorosas de priorização de campo:
* 🔴 **CRÍTICA:** $Score \ge 4.5$
* 🟠 **ALTA:** $Score \ge 2.5$
* 🟡 **MÉDIA:** $Score \ge 0.8$
* 🔵 **BAIXA:** $Score < 0.8$

---

## 🗄️ Estrutura do Repositório no GitHub

O repositório está estruturado de forma modular, separando a aplicação em produção, o banco de dados otimizado e os scripts de processamento:

```text
.
├── .streamlit/
│   └── config.toml                     # Configurações de interface e tema visual do painel
├── dados/                              # Banco de dados otimizado no formato nativo GeoParquet
│   ├── rios/                           # Diretório de hidrografia de alta fidelidade ANA (Tolerância: 25m)
│   │   ├── rios_sp.parquet             # Fragmentos colunares do estado de São Paulo (6.57 MB)
│   │   ├── rios_mg.parquet             # Fragmentos colunares do estado de Minas Gerais (20.30 MB)
│   │   └── ...                         # Demais unidades da federação fatiadas (rios_ba, rios_pr, etc.)
│   ├── malha_ferroviaria.parquet       # Eixos de trilhos nacionais estruturados para grafos (12.73 MB)
│   ├── unidades_conservacao.parquet    # Polígonos de UCs federais e estaduais mapeadas
│   ├── terras_indigenas.parquet        # Polígonos de áreas demarcadas e homologadas (Funai)
│   ├── areas_risco.parquet             # Setores de risco a deslizamento e inundação (SGB/CPRM)
│   ├── setores_sp.parquet              # Polígonos de adensamento demográfico urbano (IBGE)
│   ├── rodovias.parquet                # Malha rodoviária integrada (cruzamentos de PNs)
│   └── patios_oficinas.parquet         # Pontos estratégicos e pátios operacionais técnicos (1.003 registros)
├── processar_dados/                    # Módulos de ETL: Scripts de engenharia e limpeza de dados
│   ├── auditar_patios.py               # Script de diagnóstico para metadados e colunas brutas de SIG
│   ├── processar_ferrovias.py          # Harmonização, tratamento de strings e codificação PNV
│   ├── processar_hidrografia.py        # Fatiador nacional do GPKG massivo da ANA para Parquet por UF
│   ├── processar_patios.py             # Filtro, tratamento e estruturação dos pontos logísticos do GeoDNIT
│   ├── processar_perigo_sgb.py         # Padronização de classes de criticidade de risco do SGB
│   ├── processar_setores_sp.py         # Filtro de alta densidade demográfica por km²
│   ├── processar_terras_indigenas.py   # Dissolve e simplificação de polígonos da Funai
│   └── processar_unidades_conservacao.py # Estruturação de restrições por grau de proteção
├── .gitignore                          # Restrição de subida de arquivos brutos/temporários (.zip, .gpkg, .shp)
├── packages.txt                        # Dependências a nível de S.O. para o container Linux (GDAL, PROJ)
├── requirements.txt                    # Dependências de bibliotecas Python para instalação via pip (PyArrow, Geobr)
└── viaprev.py                          # Script principal da aplicação (Interface Streamlit e Motores)
```

⚙️ Fluxo de Engenharia de Dados (ETL Layer)
Para manter a aplicação responsiva rodando sob os limites estritos de hardware do Streamlit Community Cloud, todas as bases cartográficas brutas passam por uma triagem e otimização rigorosa:

Redução de Atributos (Drop Columns): São removidas colunas alfanuméricas redundantes de metadados textuais pesados, mantendo apenas identificadores técnicos essenciais para fins de cruzamento e rotulagem (ex: nome_uc, classe_risco, cocursodag).

Particionamento por Unidade da Federação: Para mitigar o gargalo de arquivos massivos (como o GeoPackage original de hidrografia da ANA de 674 MB), a base é fatiada nas fronteiras estaduais. Em tempo de execução, o aplicativo detecta quais estados a malha ferroviária intercepta e faz o carregamento via RAM apenas dos arquivos rios_{uf}.parquet necessários, aplicando filtros de caixa envolvente (Bounding Box) na leitura física do disco.

Casamento de Tolerância Cartográfica: O pipeline do ETL de hidrografia adota uma tolerância geométrica estrita de 25 metros (via simplificação Douglas-Peucker), preservando curvas sinuosas críticas de montanha na engenharia SIG. No frontend, a função otimizar_camada_para_mapa aplica um gpd.clip no corredor de 1.5 km combinado com um .explode() geométrico e simplificação dinâmica de 0.0003 graus, limpando artefatos e garantindo uma renderização fluida no navegador.

Camadas de Processamento em Background (Bastidores): A camada de adensamento populacional (setores_sp.parquet) opera de forma 100% silenciosa. Devido ao peso extremo de dezenas de milhares de polígonos urbanos do IBGE que esgotariam a memória de tela, a intersecção espacial ocorre puramente em memória RAM para calcular o score final e as cores de criticidade das diretrizes diárias, poupando o canvas do mapa de sobrecargas vetoriais.

Resiliência Multiplataforma: Injeção dinâmica do diretório de dados cartográficos via pyproj.datadir no ecossistema macOS/Anaconda local, blindando o fluxo contra falhas de falta de contexto de projeção (proj.db) durante gravações estruturadas via pyarrow.
