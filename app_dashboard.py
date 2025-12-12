import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import ast

# Importar módulos locales
import config
import services
import ui

# --- 1. CONFIGURACIÓN DE PÁGINA Y ESTILOS ---
st.set_page_config(
    page_title="Alrotek Monitor v1", 
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Cargar estilos
ui.load_styles()

# --- 5. INTERFAZ ---
st.image("logo.png", width=100)
st.title("Alrotek Monitor v1")

with st.expander("⚙️ Configuración", expanded=True):
    col_conf1, col_conf2 = st.columns(2)
    with col_conf1: tc_usd = st.number_input("TC (USD -> CRC)", value=515)
    with col_conf2: st.info(f"TC: ₡{tc_usd}")

# SE AGREGÓ 'tab_down' AL FINAL
tab_kpis, tab_renta, tab_prod, tab_inv, tab_cx, tab_cli, tab_vend, tab_det, tab_down = st.tabs(["📊 Visión General", "📈 Rentabilidad Proyectos", "📦 Productos", "🕸️ Baja Rotación", "💰 Cartera", "👥 Segmentación", "💼 Vendedores", "🔍 Radiografía", "📥 Descargas"])

with st.spinner('Cargando...'):
    df_main = services.cargar_datos_generales()
    df_metas = services.cargar_metas()
    df_prod = services.cargar_detalle_productos()
    df_an = services.cargar_estructura_analitica()
    
    if not df_main.empty:
        df_info = services.cargar_datos_clientes_extendido(df_main['ID_Cliente'].unique().tolist())
        if not df_info.empty:
            df_main = pd.merge(df_main, df_info, on='ID_Cliente', how='left')
            df_main[['Provincia', 'Zona_Comercial', 'Categoria_Cliente']] = df_main[['Provincia', 'Zona_Comercial', 'Categoria_Cliente']].fillna('Sin Dato')
        else:
            # FIX: Inicializar columnas vacías si falla la carga extendida
            df_main['Provincia'] = 'Sin Dato'
            df_main['Zona_Comercial'] = 'Sin Dato'
            df_main['Categoria_Cliente'] = 'Sin Dato'

# === PESTAÑA 1: VISIÓN GENERAL ===
with tab_kpis:
    if not df_main.empty:
        col_f, _ = st.columns([1,3])
        with col_f: anio_sel = st.selectbox("📅 Año Fiscal", sorted(df_main['invoice_date'].dt.year.unique(), reverse=True))
        df_anio = df_main[df_main['invoice_date'].dt.year == anio_sel]
        df_ant = df_main[df_main['invoice_date'].dt.year == (anio_sel - 1)]
        
        venta = df_anio['Venta_Neta'].sum()
        delta = ((venta - df_ant['Venta_Neta'].sum()) / df_ant['Venta_Neta'].sum() * 100) if df_ant['Venta_Neta'].sum() > 0 else 0
        meta = df_metas[df_metas['Anio'] == anio_sel]['Meta'].sum()
        
        c1, c2, c3, c4 = st.columns(4)
        with c1: ui.card_kpi("Venta Total", venta, "border-green", f"{delta:+.1f}% vs Anterior")
        with c2: ui.card_kpi("Meta Anual", meta, "bg-dark-blue", formato="moneda")
        with c3: ui.card_kpi("Cumplimiento", f"{(venta/meta*100) if meta>0 else 0:.1f}%", "border-blue", formato="raw")
        with c4: ui.card_kpi("Ticket Prom.", (venta/df_anio['name'].nunique()) if df_anio['name'].nunique()>0 else 0, "border-purple")
        
        st.divider()
        st.download_button("📥 Descargar", data=ui.convert_df_to_excel(df_anio[['invoice_date', 'name', 'Cliente', 'amount_untaxed_signed']]), file_name=f"Ventas_{anio_sel}.xlsx")

        st.markdown(f"### 🎯 Cumplimiento de Meta ({anio_sel})")
        v_act = df_anio.groupby('Mes_Num')['Venta_Neta'].sum().reset_index().rename(columns={'Venta_Neta': 'Actual'})
        v_meta = df_metas[df_metas['Anio'] == anio_sel].groupby('Mes_Num')['Meta'].sum().reset_index()
        df_gm = pd.DataFrame({'Mes_Num': range(1, 13)}).merge(v_act, on='Mes_Num', how='left').merge(v_meta, on='Mes_Num', how='left').fillna(0)
        df_gm['Mes'] = df_gm['Mes_Num'].map({1:'Ene',2:'Feb',3:'Mar',4:'Abr',5:'May',6:'Jun',7:'Jul',8:'Ago',9:'Sep',10:'Oct',11:'Nov',12:'Dic'})
        
        fig_m = go.Figure()
        fig_m.add_trace(go.Bar(x=df_gm['Mes'], y=df_gm['Actual'], name='Actual', marker_color=['#2ecc71' if r>=m else '#e74c3c' for r,m in zip(df_gm['Actual'], df_gm['Meta'])]))
        fig_m.add_trace(go.Scatter(x=df_gm['Mes'], y=df_gm['Meta'], name='Meta', line=dict(color='#f1c40f', width=3, dash='dash')))
        st.plotly_chart(ui.config_plotly(fig_m), use_container_width=True)

        st.divider()
        st.markdown(f"### 🗓️ Comparativo: {anio_sel} vs {anio_sel-1}")
        v_ant_g = df_ant.groupby('Mes_Num')['Venta_Neta'].sum().reset_index().rename(columns={'Venta_Neta': 'Anterior'})
        df_gc = pd.DataFrame({'Mes_Num': range(1, 13)}).merge(v_act, on='Mes_Num', how='left').merge(v_ant_g, on='Mes_Num', how='left').fillna(0)
        df_gc['Mes'] = df_gc['Mes_Num'].map({1:'Ene',2:'Feb',3:'Mar',4:'Abr',5:'May',6:'Jun',7:'Jul',8:'Ago',9:'Sep',10:'Oct',11:'Nov',12:'Dic'})
        
        fig_c = go.Figure()
        fig_c.add_trace(go.Bar(x=df_gc['Mes'], y=df_gc['Actual'], name=f'{anio_sel}', marker_color='#2980b9'))
        fig_c.add_trace(go.Bar(x=df_gc['Mes'], y=df_gc['Anterior'], name=f'{anio_sel-1}', marker_color='#95a5a6'))
        st.plotly_chart(ui.config_plotly(fig_c), use_container_width=True)

# --- NUEVO: GRÁFICO VENTAS SEMANA ACTUAL ---
        st.divider()
        st.markdown("### 📅 Ventas Semana Actual")
        
        hoy = datetime.now()
        # Calcular lunes (0) y domingo (6) de la semana actual
        inicio_semana = hoy - timedelta(days=hoy.weekday())
        fin_semana = inicio_semana + timedelta(days=6)
        
        # Filtrar datos de la semana actual
        mask_semana = (df_main['invoice_date'].dt.date >= inicio_semana.date()) & \
                      (df_main['invoice_date'].dt.date <= fin_semana.date())
        df_semana = df_main[mask_semana].copy()
        
        if not df_semana.empty:
            # Mapeo manual para asegurar nombres en español
            df_semana['Dia_Num'] = df_semana['invoice_date'].dt.weekday
            mapa_dias = {0: 'Lunes', 1: 'Martes', 2: 'Miércoles', 3: 'Jueves', 4: 'Viernes', 5: 'Sábado', 6: 'Domingo'}
            df_semana['Dia_Nom'] = df_semana['Dia_Num'].map(mapa_dias)
            
            # Agrupar y ordenar
            v_semana = df_semana.groupby(['Dia_Num', 'Dia_Nom'])['Venta_Neta'].sum().reset_index().sort_values('Dia_Num')
            
            # Crear gráfico
            fig_w = px.bar(v_semana, x='Dia_Nom', y='Venta_Neta', text_auto='.2s', 
                           title=f"Semana del {inicio_semana.strftime('%d/%m')} al {fin_semana.strftime('%d/%m')}")
            fig_w.update_traces(marker_color='#1abc9c') # Color cian para diferenciar
            st.plotly_chart(ui.config_plotly(fig_w), use_container_width=True)
        else:
            st.info(f"💤 No hay ventas registradas aún en la semana del {inicio_semana.strftime('%d/%m')}.")
        
        st.divider()
        c_mix, c_top = st.columns(2)
        with c_mix:
            st.subheader("📊 Mix por Plan")
            if not df_prod.empty:
                df_l = df_prod[df_prod['date'].dt.year == anio_sel].copy()
                mapa = dict(zip(df_an['id_cuenta_analitica'].astype(str), df_an['Plan_Nombre'])) if not df_an.empty else {}
                def clasif(d):
                    if not d: return "Retail"
                    try: return mapa.get(str(list((d if isinstance(d,dict) else ast.literal_eval(str(d))).keys())[0]), "Otro")
                    except: return "Otro"
                df_l['Plan'] = df_l['analytic_distribution'].apply(clasif)
                
                df_l['Mes_Num'] = df_l['date'].dt.month
                df_l['Mes_Nom'] = df_l['date'].dt.strftime('%m-%b')
                
                df_grp = df_l.groupby(['Mes_Num', 'Mes_Nom', 'Plan'])['Venta_Neta'].sum().reset_index().sort_values('Mes_Num')
                
                # --- NUEVO: Cálculo de % por mes ---
                # 1. Calcular el total vendido por mes para usarlo de base (100%)
                df_grp['Total_Mes'] = df_grp.groupby('Mes_Num')['Venta_Neta'].transform('sum')
                
                # 2. Calcular el porcentaje formateado (ej. 25.4%)
                df_grp['Pct_Texto'] = df_grp.apply(lambda x: f"{x['Venta_Neta']/x['Total_Mes']:.1%}" if x['Total_Mes'] != 0 else "0%", axis=1)
                
                # 3. Crear gráfico incluyendo el texto
                fig_mix = px.bar(df_grp, x='Mes_Nom', y='Venta_Neta', color='Plan', 
                                 text='Pct_Texto',  # Aquí asignamos el porcentaje como texto
                                 title="")
                
                # 4. Ajustar para que el texto se vea bien dentro de la barra
                fig_mix.update_traces(textposition='inside', textfont_size=10)
                
                st.plotly_chart(ui.config_plotly(fig_mix), use_container_width=True)
       
        with c_top:
            st.subheader("🏆 Top Vendedores")
            r_act = df_anio.groupby('Vendedor')['Venta_Neta'].sum().reset_index()
            r_ant = df_ant.groupby('Vendedor')['Venta_Neta'].sum().reset_index().rename(columns={'Venta_Neta':'Venta_Ant'})
            r_fin = pd.merge(r_act, r_ant, on='Vendedor', how='left').fillna(0)
            
            def txt(row):
                d = ((row['Venta_Neta'] - row['Venta_Ant'])/row['Venta_Ant']*100) if row['Venta_Ant']>0 else 100
                i = "⬆️" if d>=0 else "⬇️"
                return f"₡{row['Venta_Neta']/1e6:.1f}M {i} {d:.0f}%"
            
            r_fin['T'] = r_fin.apply(txt, axis=1)
            st.plotly_chart(ui.config_plotly(go.Figure(go.Bar(x=r_fin.sort_values('Venta_Neta').tail(15)['Venta_Neta'], y=r_fin.sort_values('Venta_Neta').tail(15)['Vendedor'], orientation='h', text=r_fin.sort_values('Venta_Neta').tail(15)['T'], textposition='auto', marker_color='#2ecc71'))), use_container_width=True)

# === PESTAÑA 2: PROYECTOS (ESTRUCTURA v10.7) ===
with tab_renta:
    df_pnl = services.cargar_pnl_historico()
    if not df_an.empty:
        c1, c2 = st.columns(2)
        mapa_c = dict(zip(df_an['id_cuenta_analitica'].astype(float), df_an['Plan_Nombre']))
        mapa_n = dict(zip(df_an['id_cuenta_analitica'].astype(float), df_an['Cuenta_Nombre']))
        
        with c1: planes = st.multiselect("Planes:", sorted(list(set(mapa_c.values()))))
        posibles = [id for id, p in mapa_c.items() if p in planes] if planes else []
        nombres = [mapa_n[id] for id in posibles]
        with c2: proys = st.multiselect("Proyectos:", sorted(nombres))
        
        if proys:
            sel_ids = [id for id, n in mapa_n.items() if n in proys]
            df_f = df_pnl[df_pnl['id_cuenta_analitica'].isin(sel_ids)] if not df_pnl.empty else pd.DataFrame()
            totales = {k: abs(df_f[df_f['Clasificacion']==k]['Monto_Neto'].sum()) if not df_f.empty else 0 
                      for k in ['Venta','Instalación','Suministros','WIP','Provisión','Costo Retail','Otros Gastos']}
            totales['Ajustes Inv'] = df_f[df_f['Clasificacion']=='Ajustes Inv']['Monto_Neto'].sum() if not df_f.empty else 0
            
            # Cargas Operativas
            df_h = services.cargar_detalle_horas_mes(sel_ids)
            df_s, _, bods = services.cargar_inventario_ubicacion_proyecto_v4(sel_ids, proys)
            df_c = services.cargar_compras_pendientes_v7_json_scanner(sel_ids, tc_usd)
            df_fe = services.cargar_facturacion_estimada_v2(sel_ids, tc_usd)
            
            # CALCULOS FINALES v10.7 (ALERTA OPERATIVA)
            # 1. Ingresos (Total Proyecto)
            total_fact = totales['Venta']
            total_pend = df_fe['Monto_CRC'].sum() if not df_fe.empty else 0
            total_ing = total_fact + total_pend
            
            # 2. Costo Operativo (TRANSITORIO - SOLO ALERTA)
            costo_vivo = (
                (df_s['Valor_Total'].sum() if not df_s.empty else 0) + # Inventario
                totales['WIP'] + # WIP
                (df_c['Monto_Pendiente'].sum() if not df_c.empty else 0) + # Compras Pend
                (df_h['Costo'].sum() if not df_h.empty else 0) # Horas
            )
            
            # 3. Margen Alerta (Ingreso Total - Costo Vivo)
            margen_alerta = total_ing - costo_vivo
            pct_alerta = (margen_alerta / total_ing * 100) if total_ing > 0 else 0
            
            color_alerta = "bg-alert-green" if pct_alerta > 30 else ("bg-alert-warn" if pct_alerta > 10 else "bg-alert-red")

            st.markdown("#### 🚦 Semáforo de Alerta Operativa")
            st.caption("Margen calculado como: (Total Ingresos - Costos Vivos). Excluye costos contables cerrados y provisiones.")
            
            k1, k2, k3, k4 = st.columns(4)
            with k1: ui.card_kpi("Ingreso Total Proy.", total_ing, "border-green")
            with k2: ui.card_kpi("Costo Vivo (Alerta)", costo_vivo, "border-red")
            with k3: ui.card_kpi("MARGEN ALERTA", margen_alerta, color_alerta)
            with k4: ui.card_kpi("% Cobertura", pct_alerta, "border-blue", formato="percent")
            
            st.divider()
            
            st.markdown("#### 📥 Flujo de Ingresos")
            i1, i2 = st.columns(2)
            with i1: ui.card_kpi("Facturado (Real)", total_fact, "border-green")
            with i2: ui.card_kpi("Por Facturar (Pendiente)", total_pend, "border-gray")
            
            st.divider()

            # LADO A LADO (IZQ: FIRMES / DER: TRANSITORIOS)
            c_izq, c_der = st.columns(2)
            
            with c_izq:
                st.markdown("#### 📚 Costos Firmes (Contables - YA CERRADOS)")
                st.caption("Estos costos NO restan en el semáforo de alerta.")
                ui.card_kpi("Instalación", totales['Instalación'], "border-orange")
                ui.card_kpi("Suministros", totales['Suministros'], "border-orange")
                ui.card_kpi("Costo Venta (Retail)", totales['Costo Retail'], "border-orange")
                ui.card_kpi("Ajustes Inv.", totales['Ajustes Inv'], "border-gray")
                ui.card_kpi("Otros Gastos", totales['Otros Gastos'], "border-gray")

            with c_der:
                st.markdown("#### ⚙️ Costos Transitorios (Vivos - ALERTA)")
                st.caption("Estos costos SÍ restan en el semáforo.")
                ui.card_kpi("Inventario en Sitio", df_s['Valor_Total'].sum() if not df_s.empty else 0, "border-purple")
                ui.card_kpi("WIP (En Proceso)", totales['WIP'], "border-yellow")
                ui.card_kpi("Compras Pendientes", df_c['Monto_Pendiente'].sum() if not df_c.empty else 0, "border-teal")
                ui.card_kpi("Mano de Obra (Horas)", df_h['Costo'].sum() if not df_h.empty else 0, "border-blue")
                st.markdown("---")
                ui.card_kpi("Provisiones (Informativo)", totales['Provisión'], "border-purple", "Reserva contable (No suma)") 
            
            st.divider()
            t1, t2, t3, t4 = st.tabs(["Inventario", "Compras", "Contabilidad", "Fact. Pend."])
            with t1: st.dataframe(df_s, use_container_width=True)
            with t2: st.dataframe(df_c, use_container_width=True)
            with t3: st.dataframe(df_f, use_container_width=True)
            with t4: st.dataframe(df_fe, use_container_width=True)

# === PESTAÑA 3: PRODUCTOS (ACTUALIZADA: Métrica + Cat + Zona + Vendedor) ===
with tab_prod:
    df_cat = services.cargar_inventario_general()
    if not df_prod.empty:
        # --- 1. FILTROS GENERALES ---
        c_f1, c_f2 = st.columns([1, 4])
        with c_f1: 
            anio = st.selectbox("📅 Año", sorted(df_prod['date'].dt.year.unique(), reverse=True), key="prod_anio_sel")
        with c_f2: 
            # Selector de métrica (Afecta a TODOS los gráficos)
            tipo_ver = st.radio("📊 Ver Gráficos por:", 
                                ["Monto (₡)", "Cantidad (Und)", "Freq. Facturas (# Docs)"], 
                                index=0, horizontal=True, key="prod_metric_sel")
        
        # --- CONFIGURACIÓN DINÁMICA ---
        if "Monto" in tipo_ver:
            col_calc = 'Venta_Neta'
            agg_func = 'sum'
            fmt_text = '.2s'
        elif "Cantidad" in tipo_ver:
            col_calc = 'quantity'
            agg_func = 'sum'
            fmt_text = '.2s'
        else:
            col_calc = 'ID_Factura'
            agg_func = 'nunique' # Conteo único de facturas
            fmt_text = ''
        
        # Filtrar datos base por año
        df_p = df_prod[df_prod['date'].dt.year == anio].merge(df_cat[['ID_Producto','Tipo']], on='ID_Producto', how='left').fillna({'Tipo':'Otro'})
        
        # --- 2. GRÁFICOS GLOBALES ---
        c_m1, c_m2 = st.columns([1, 2])
        
        # Mix por Tipo (Con altura ajustada y padding)
        grp_tipo = df_p.groupby('Tipo')[col_calc].agg(agg_func).reset_index()
        with c_m1: 
            fig_pie = px.pie(grp_tipo, values=col_calc, names='Tipo', 
                             title=f"Mix por Tipo ({tipo_ver})", 
                             height=300)
            fig_pie.update_layout(title_pad=dict(b=20), margin=dict(t=50, b=10, l=10, r=10))
            st.plotly_chart(ui.config_plotly(fig_pie), use_container_width=True)
        
        # Top 10 Global
        grp_top = df_p.groupby('Producto')[col_calc].agg(agg_func).sort_values().tail(10).reset_index()
        with c_m2: 
            st.plotly_chart(ui.config_plotly(px.bar(grp_top, x=col_calc, y='Producto', orientation='h', text_auto=fmt_text, title=f"Top 10 Global ({tipo_ver})")), use_container_width=True)

        # --- PREPARACIÓN DE DATOS DETALLADOS ---
        if not df_main.empty:
            # ACTUALIZACIÓN: Ahora traemos también 'Vendedor' en el merge
            df_merged = pd.merge(df_p, df_main[['id', 'Categoria_Cliente', 'Zona_Comercial', 'Vendedor']], left_on='ID_Factura', right_on='id', how='left')
            df_merged['Categoria_Cliente'] = df_merged['Categoria_Cliente'].fillna("Sin Categoría")
            df_merged['Zona_Comercial'] = df_merged['Zona_Comercial'].fillna("Sin Zona")
            df_merged['Vendedor'] = df_merged['Vendedor'].fillna("Sin Asignar")

            st.divider()
            
            # --- 3. POR CATEGORÍA DE CLIENTE ---
            c_cat1, c_cat2 = st.columns([1, 3])
            with c_cat1: 
                st.subheader(f"🛍️ Por Categoría")
                cats = sorted(df_merged['Categoria_Cliente'].unique())
                cat_sel = st.selectbox("Filtrar Categoría:", cats, key="prod_cat_filter")
            
            with c_cat2:
                df_cf = df_merged[df_merged['Categoria_Cliente'] == cat_sel]
                if not df_cf.empty:
                    top_cat = df_cf.groupby('Producto')[col_calc].agg(agg_func).sort_values().tail(10).reset_index()
                    fig_cat = px.bar(top_cat, x=col_calc, y='Producto', orientation='h', text_auto=fmt_text, 
                                     title=f"Top Productos: {cat_sel}", color_discrete_sequence=['#8e44ad']) # Morado
                    st.plotly_chart(ui.config_plotly(fig_cat), use_container_width=True)
                else:
                    st.info("Sin datos.")

            st.divider()

            # --- 4. POR ZONA COMERCIAL ---
            c_zon1, c_zon2 = st.columns([1, 3])
            with c_zon1: 
                st.subheader(f"🌍 Por Zona")
                zonas = sorted(df_merged['Zona_Comercial'].unique())
                zona_sel = st.selectbox("Filtrar Zona:", zonas, key="prod_zona_filter")
            
            with c_zon2:
                df_zf = df_merged[df_merged['Zona_Comercial'] == zona_sel]
                if not df_zf.empty:
                    top_zona = df_zf.groupby('Producto')[col_calc].agg(agg_func).sort_values().tail(10).reset_index()
                    fig_zona = px.bar(top_zona, x=col_calc, y='Producto', orientation='h', text_auto=fmt_text, 
                                     title=f"Top Productos: {zona_sel}", color_discrete_sequence=['#16a085']) # Teal/Verde
                    st.plotly_chart(ui.config_plotly(fig_zona), use_container_width=True)
                else:
                    st.info("Sin datos.")

            st.divider()

            # --- 5. POR VENDEDOR (NUEVO) ---
            c_ven1, c_ven2 = st.columns([1, 3])
            with c_ven1: 
                st.subheader(f"👤 Por Vendedor")
                vendedores = sorted(df_merged['Vendedor'].unique())
                vend_sel = st.selectbox("Filtrar Vendedor:", vendedores, key="prod_vend_filter")
            
            with c_ven2:
                df_vf = df_merged[df_merged['Vendedor'] == vend_sel]
                if not df_vf.empty:
                    top_vend = df_vf.groupby('Producto')[col_calc].agg(agg_func).sort_values().tail(10).reset_index()
                    fig_vend = px.bar(top_vend, x=col_calc, y='Producto', orientation='h', text_auto=fmt_text, 
                                     title=f"Top Productos: {vend_sel}", color_discrete_sequence=['#d35400']) # Naranja Oscuro
                    st.plotly_chart(ui.config_plotly(fig_vend), use_container_width=True)
                else:
                    st.info("Sin datos.")
# === PESTAÑA 4: BAJA ROTACIÓN ===
with tab_inv:
    if st.button("🔄 Calcular Rotación"):
        df_h, status = services.cargar_inventario_baja_rotacion()
        if not df_h.empty:
            days = st.slider("Días Inactivo:", 0, 720, 365)
            df_show = df_h[df_h['Dias_Sin_Salida'] >= days]
            c1, c2, c3 = st.columns(3)
            with c1: ui.card_kpi("Capital Estancado", df_show['Valor'].sum(), "border-red")
            with c2: ui.card_kpi("Total Items", len(df_h), "border-gray", formato="numero")
            with c3: ui.card_kpi("Items Críticos", len(df_show), "border-orange", formato="numero")
            st.dataframe(df_show[['Producto','Ubicacion','quantity','Dias_Sin_Salida','Valor']], use_container_width=True)
        else: st.info(status)

# === PESTAÑA 5: CARTERA ===
with tab_cx:
    df_cx = services.cargar_cartera()
    if not df_cx.empty:
        deuda = df_cx['amount_residual'].sum()
        vencido = df_cx[df_cx['Dias_Vencido']>0]['amount_residual'].sum()
        c1, c2, c3 = st.columns(3)
        with c1: ui.card_kpi("Por Cobrar", deuda, "border-blue")
        with c2: ui.card_kpi("Vencido", vencido, "border-red")
        with c3: ui.card_kpi("Salud", f"{(1-(vencido/deuda))*100:.1f}% al día" if deuda>0 else "100%", "border-green", formato="raw")
        c_g, c_t = st.columns([2,1])
        with c_g:
            df_b = df_cx.groupby('Antiguedad')['amount_residual'].sum().reset_index()
            st.plotly_chart(ui.config_plotly(px.bar(df_b, x='Antiguedad', y='amount_residual', text_auto='.2s', color='Antiguedad')), use_container_width=True)
        with c_t:
            st.dataframe(df_cx.groupby('Cliente')['amount_residual'].sum().sort_values(ascending=False).head(10), use_container_width=True)

# === PESTAÑA 6: SEGMENTACIÓN ===
with tab_cli:
    if not df_main.empty:
        anio_c = st.selectbox("Año", sorted(df_main['invoice_date'].dt.year.unique(), reverse=True), key="sc")
        df_c = df_main[df_main['invoice_date'].dt.year == anio_c]
        c1, c2, c3 = st.columns(3)
        with c1: st.plotly_chart(ui.config_plotly(px.pie(df_c.groupby('Provincia')['Venta_Neta'].sum().reset_index(), values='Venta_Neta', names='Provincia')), use_container_width=True)
        with c2: st.plotly_chart(ui.config_plotly(px.pie(df_c.groupby('Zona_Comercial')['Venta_Neta'].sum().reset_index(), values='Venta_Neta', names='Zona_Comercial')), use_container_width=True)
        with c3: st.plotly_chart(ui.config_plotly(px.pie(df_c.groupby('Categoria_Cliente')['Venta_Neta'].sum().reset_index(), values='Venta_Neta', names='Categoria_Cliente')), use_container_width=True)
        st.divider()
        df_old = df_main[df_main['invoice_date'].dt.year == (anio_c - 1)]
        cli_now = set(df_c['Cliente'])
        cli_old = set(df_old['Cliente'])
        nuevos = list(cli_now - cli_old)
        perdidos = list(cli_old - cli_now)
        k1, k2, k3, k4 = st.columns(4)
        with k1: ui.card_kpi("Activos", len(cli_now), "border-blue", formato="numero")
        with k2: ui.card_kpi("Nuevos", len(nuevos), "border-green", formato="numero")
        with k3: ui.card_kpi("Churn", len(perdidos), "border-red", formato="numero")
        with k4: ui.card_kpi("Retención", f"{len(cli_old.intersection(cli_now))/len(cli_old)*100:.1f}%" if cli_old else "100%", "border-purple", formato="raw")
        c_top, c_lost = st.columns(2)
        with c_top:
            st.subheader("Top Clientes")
            df_top = df_c.groupby('Cliente')['Venta_Neta'].sum().sort_values().tail(10).reset_index()
            st.plotly_chart(ui.config_plotly(px.bar(df_top, x='Venta_Neta', y='Cliente', orientation='h', text_auto='.2s')), use_container_width=True)
        with c_lost:
            st.subheader("Oportunidad (Perdidos)")
            if perdidos:
                df_l = df_old[df_old['Cliente'].isin(perdidos)].groupby('Cliente')['Venta_Neta'].sum().sort_values().tail(10).reset_index()
                st.plotly_chart(ui.config_plotly(px.bar(df_l, x='Venta_Neta', y='Cliente', orientation='h', text_auto='.2s', color_discrete_sequence=['#e74c3c'])), use_container_width=True)

# === PESTAÑA 7: VENDEDORES ===
with tab_vend:
    if not df_main.empty:
        c1, c2 = st.columns(2)
        with c1: anio_v = st.selectbox("Año", sorted(df_main['invoice_date'].dt.year.unique(), reverse=True), key="sv")
        with c2: vend = st.selectbox("Vendedor", sorted(df_main['Vendedor'].unique()))
        df_v = df_main[(df_main['invoice_date'].dt.year == anio_v) & (df_main['Vendedor'] == vend)]
        df_v_old = df_main[(df_main['invoice_date'].dt.year == (anio_v-1)) & (df_main['Vendedor'] == vend)]
        perdidos_v = list(set(df_v_old['Cliente']) - set(df_v['Cliente']))
        k1, k2, k3 = st.columns(3)
        with k1: ui.card_kpi("Venta", df_v['Venta_Neta'].sum(), "border-green")
        with k2: ui.card_kpi("Clientes", df_v['Cliente'].nunique(), "border-blue", formato="numero")
        with k3: ui.card_kpi("Riesgo", len(perdidos_v), "border-red", formato="numero")
        c_v1, c_v2 = st.columns(2)
        with c_v1:
            st.subheader("Mejores Clientes")
            if not df_v.empty:
                df_best = df_v.groupby('Cliente')['Venta_Neta'].sum().sort_values().tail(10).reset_index()
                st.plotly_chart(ui.config_plotly(px.bar(df_best, x='Venta_Neta', y='Cliente', orientation='h', text_auto='.2s')), use_container_width=True)
        with c_v2:
            st.subheader("Cartera Perdida")
            if perdidos_v:
                df_lst = df_v_old[df_v_old['Cliente'].isin(perdidos_v)].groupby('Cliente')['Venta_Neta'].sum().sort_values().tail(10).reset_index()
                st.plotly_chart(ui.config_plotly(px.bar(df_lst, x='Venta_Neta', y='Cliente', orientation='h', text_auto='.2s', color_discrete_sequence=['#e74c3c'])), use_container_width=True)

# === PESTAÑA 8: RADIOGRAFÍA ===
with tab_det:
    if not df_main.empty:
        cli = st.selectbox("Buscar Cliente:", sorted(df_main['Cliente'].unique()), index=None, placeholder="Escriba para buscar...")
        if cli:
            df_cl = df_main[df_main['Cliente'] == cli]
            ultima = df_cl['invoice_date'].max()
            dias = (datetime.now() - ultima).days
            k1, k2, k3, k4 = st.columns(4)
            with k1: ui.card_kpi("Total Histórico", df_cl['Venta_Neta'].sum(), "border-green")
            with k2: ui.card_kpi("Última Compra", ultima.strftime('%d-%m-%Y'), "border-blue", formato="raw")
            with k3: ui.card_kpi("Días Inactivo", dias, "border-red" if dias>90 else "border-gray", formato="numero")
            with k4: ui.card_kpi("Ubicación", df_cl.iloc[0]['Provincia'], "border-purple", formato="raw")
            c_h, c_p = st.columns(2)
            with c_h:
                st.subheader("Historial")
                hist = df_cl.groupby(df_cl['invoice_date'].dt.year)['Venta_Neta'].sum().reset_index()
                st.plotly_chart(ui.config_plotly(px.bar(hist, x='invoice_date', y='Venta_Neta', text_auto='.2s')), use_container_width=True)
            with c_p:
                st.subheader("Top Productos")
                if not df_prod.empty:
                    df_cp = df_prod[df_prod['ID_Factura'].isin(df_cl['id'])]
                    top = df_cp.groupby('Producto')['Venta_Neta'].sum().sort_values().tail(10).reset_index()
                    st.plotly_chart(ui.config_plotly(px.bar(top, x='Venta_Neta', y='Producto', orientation='h', text_auto='.2s')), use_container_width=True)

# === PESTAÑA 9: CENTRO DE DESCARGAS ===
with tab_down:
    st.header("📥 Centro de Descargas")
    st.markdown("Descargue aquí los datos utilizados para generar los gráficos del dashboard.")
    
    col_d1, col_d2 = st.columns(2)
    
    # --- SECCIÓN 1: VENTAS Y GENERAL ---
    with col_d1:
        st.subheader("📊 Ventas y Visión General")
        
        # 1. Ventas Generales (Todas)
        if not df_main.empty:
            buffer_main = ui.convert_df_to_excel(df_main[['invoice_date', 'name', 'Cliente', 'Vendedor', 'Venta_Neta', 'Provincia', 'Zona_Comercial', 'Categoria_Cliente']], "Ventas_General")
            st.download_button("📥 Ventas Históricas (Detalle Facturas)", data=buffer_main, file_name="Ventas_Generales.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        
        # 2. Ventas Semana Actual (Recalculado)
        hoy = datetime.now()
        start_week = hoy - timedelta(days=hoy.weekday())
        end_week = start_week + timedelta(days=6)
        if not df_main.empty:
            mask_week = (df_main['invoice_date'].dt.date >= start_week.date()) & (df_main['invoice_date'].dt.date <= end_week.date())
            df_week_dl = df_main[mask_week][['invoice_date', 'name', 'Cliente', 'Venta_Neta']].copy()
            if not df_week_dl.empty:
                st.download_button(f"📥 Ventas Semana Actual ({start_week.strftime('%d/%m')})", 
                                   data=ui.convert_df_to_excel(df_week_dl), file_name=f"Ventas_Semana_{start_week.strftime('%d-%m')}.xlsx")
            else:
                st.warning("No hay ventas esta semana para descargar.")

        # 3. Mix por Plan (Analítico)
        if not df_prod.empty and not df_an.empty:
             # Reutilizamos lógica de mapeo simple para descarga
            mapa_dl = dict(zip(df_an['id_cuenta_analitica'].astype(str), df_an['Plan_Nombre']))
            def get_plan(d):
                try: return mapa_dl.get(str(list((d if isinstance(d,dict) else ast.literal_eval(str(d))).keys())[0]), "Otro")
                except: return "Retail/Otro"
            
            df_mix_dl = df_prod.copy()
            df_mix_dl['Plan'] = df_mix_dl['analytic_distribution'].apply(get_plan)
            grp_mix = df_mix_dl.groupby(['Plan', df_mix_dl['date'].dt.year])['Venta_Neta'].sum().reset_index().rename(columns={'date':'Año'})
            st.download_button("📥 Mix por Plan (Resumen Anual)", data=ui.convert_df_to_excel(grp_mix), file_name="Mix_Ventas_Plan.xlsx")

    # --- SECCIÓN 2: PRODUCTOS E INVENTARIO ---
    with col_d2:
        st.subheader("📦 Productos e Inventario")
        
        # 4. Detalle de Productos
        if not df_prod.empty:
            # Preparamos un DF limpio
            df_p_clean = df_prod[['date', 'ID_Factura', 'Producto', 'quantity', 'Venta_Neta']].copy()
            st.download_button("📥 Movimientos de Productos (Todos)", data=ui.convert_df_to_excel(df_p_clean), file_name="Detalle_Productos.xlsx")
        
        # 5. Inventario Baja Rotación
        if st.button("🔄 Generar Reporte Baja Rotación (Reciente)"):
            with st.spinner("Procesando inventario..."):
                df_inv_dl, status_inv = services.cargar_inventario_baja_rotacion()
                if not df_inv_dl.empty:
                    st.download_button("📥 Descargar Baja Rotación", 
                                       data=ui.convert_df_to_excel(df_inv_dl), 
                                       file_name="Inventario_Baja_Rotacion.xlsx")
                else:
                    st.error(f"No se pudo generar: {status_inv}")

    st.divider()
    
    col_d3, col_d4 = st.columns(2)
    
    # --- SECCIÓN 3: COMERCIAL Y CARTERA ---
    with col_d3:
        st.subheader("💰 Cartera y Clientes")
        
        # 6. Cartera (Cuentas por Cobrar)
        df_cx_dl = services.cargar_cartera()
        if not df_cx_dl.empty:
            st.download_button("📥 Reporte de Cartera (CXC)", data=ui.convert_df_to_excel(df_cx_dl), file_name="Reporte_Cartera.xlsx")
            
        # 7. Segmentación (Resumen)
        if not df_main.empty:
            grp_seg = df_main.groupby(['Categoria_Cliente', 'Zona_Comercial'])['Venta_Neta'].sum().reset_index()
            st.download_button("📥 Ventas por Segmento/Zona", data=ui.convert_df_to_excel(grp_seg), file_name="Ventas_Segmentacion.xlsx")

    with col_d4:
        st.subheader("👤 Vendedores")
        
        # 8. Desempeño Vendedores
        if not df_main.empty:
            grp_vend = df_main.groupby(['Vendedor', df_main['invoice_date'].dt.year])['Venta_Neta'].sum().reset_index().rename(columns={'invoice_date':'Año'})
            st.download_button("📥 Ventas por Vendedor (Anual)", data=ui.convert_df_to_excel(grp_vend), file_name="Performance_Vendedores.xlsx")


