import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import ast
import io

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

# HELPER: Gráfico de Pastel Mejorado
def create_improved_pie(df_in, col_val, col_name, title, threshold=0.02, show_percent_only=True):
    # Agrupar y ordenar
    df_g = df_in.groupby(col_name)[col_val].sum().reset_index().sort_values(col_val, ascending=False)
    
    # Calcular %
    total = df_g[col_val].sum()
    if total == 0: return go.Figure()
    
    df_g['Pct'] = df_g[col_val] / total
    
    # Agrupar menores
    mask = df_g['Pct'] < threshold
    if mask.any():
        otros = df_g[mask][col_val].sum()
        df_g = df_g[~mask].copy()
        df_g = pd.concat([df_g, pd.DataFrame({col_name: ['Otros/Menores'], col_val: [otros]})], ignore_index=True)
    
    # Crear gráfico
    fig = px.pie(df_g, values=col_val, names=col_name, title=title, hole=0.4)
    
    # Configurar layout
    info_mode = 'percent' if show_percent_only else 'percent+label'
    fig.update_traces(textposition='inside', textinfo=info_mode)
    fig.update_layout(legend=dict(orientation="v", yanchor="top", y=1.0, xanchor="left", x=1.05))
    
    return fig


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
            st.plotly_chart(ui.config_plotly(go.Figure(go.Bar(x=r_fin.sort_values('Venta_Neta').tail(20)['Venta_Neta'], y=r_fin.sort_values('Venta_Neta').tail(20)['Vendedor'], orientation='h', text=r_fin.sort_values('Venta_Neta').tail(20)['T'], textposition='auto', marker_color='#2ecc71'))), use_container_width=True)

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

            # 4. Margen REAL (Solicitud Usuario: Total Ing - (Todos los Costos - Provisiones))
            # Costo Real = (Retail + Suministros + Instalación + Ajustes + Otros + WIP + Inv + Compras + MO) - Provisiones
            total_costo_real = (
                totales['Costo Retail'] + totales['Suministros'] + totales['Instalación'] + 
                totales['Ajustes Inv'] + totales['Otros Gastos'] + totales['WIP'] +
                (df_s['Valor_Total'].sum() if not df_s.empty else 0) + 
                (df_c['Monto_Pendiente'].sum() if not df_c.empty else 0) + 
                (df_h['Costo'].sum() if not df_h.empty else 0)
            ) - totales['Provisión']

            utilidad_real = total_ing - total_costo_real
            margen_real_pct = (utilidad_real / total_ing * 100) if total_ing > 0 else 0
            color_real = "border-green" if margen_real_pct > 20 else ("border-orange" if margen_real_pct > 0 else "border-red")

            st.markdown("#### 🚦 Semáforo de Alerta Operativa")
            st.caption("Margen calculado como: (Total Ingresos - Costos Vivos). Excluye costos contables cerrados y provisiones.")
            
            k1, k2, k3, k4, k5 = st.columns(5)
            with k1: ui.card_kpi("Ingreso Total Proy.", total_ing, "border-green")
            with k2: ui.card_kpi("Costo Vivo (Alerta)", costo_vivo, "border-red")
            with k3: ui.card_kpi("MARGEN ALERTA", margen_alerta, color_alerta)
            with k4: ui.card_kpi("% Cobertura", pct_alerta, "border-blue", formato="percent")
            with k5: ui.card_kpi("MARGEN REAL", margen_real_pct, color_real, formato="percent")
            
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
                
            st.divider()

            # --- NUEVO: PREPARACIÓN DE ESTADO DE RESULTADOS (V2) ---
            # 1. Calcular Costos del Sistema
            costos_sistema = (
                totales['Costo Retail'] + 
                totales['Instalación'] + 
                totales['Suministros'] + 
                totales['Ajustes Inv'] + 
                totales['Otros Gastos']
            )
            
            # 2. Variables Manuales (Preestablecidas en 0)
            kilometraje = 0 
            
            # 3. Calcular Utilidad Operativa (Restando costos y kilometraje)
            utilidad_operativa = total_fact - costos_sistema - kilometraje
            margen_operativo = (utilidad_operativa / total_fact) if total_fact != 0 else 0

            # 4. Construir el DataFrame Ordenado
            data_pnl = [
                {"Concepto": "INGRESOS (Facturado Real)", "Monto": total_fact, "Notas": "Dato del Sistema"},
                {"Concepto": "(-) Costo de Venta", "Monto": totales['Costo Retail'], "Notas": "Dato del Sistema"},
                {"Concepto": "(-) Costo Instalación", "Monto": totales['Instalación'], "Notas": "Dato del Sistema"},
                {"Concepto": "(-) Costo Suministros", "Monto": totales['Suministros'], "Notas": "Dato del Sistema"},
                {"Concepto": "(-) Ajustes de Inventario", "Monto": totales['Ajustes Inv'], "Notas": "Dato del Sistema"},
                {"Concepto": "(-) Otros Gastos", "Monto": totales['Otros Gastos'], "Notas": "Dato del Sistema"},
                {"Concepto": "(-) KILOMETRAJE", "Monto": kilometraje, "Notas": "MANUAL (Ingresar costo aquí)"},
                {"Concepto": "--------------------------------", "Monto": 0, "Notas": ""},
                {"Concepto": "(=) UTILIDAD OPERATIVA", "Monto": utilidad_operativa, "Notas": "Ingresos - (Costos + Km)"},
                {"Concepto": "(%) MARGEN OPERATIVO", "Monto": margen_operativo, "Notas": "Utilidad / Ingresos"},
                {"Concepto": "", "Monto": 0, "Notas": ""},
                {"Concepto": "(-) GASTO ADMINISTRATIVO (%)", "Monto": 0, "Notas": "MANUAL (Ingresar % aquí)"},
                {"Concepto": "(-) Gasto Administrativo (Monto)", "Monto": 0, "Notas": "Fórmula Excel: Utilidad Op * % Admin"},
                {"Concepto": "(=) UTILIDAD FINAL", "Monto": 0, "Notas": "Fórmula Excel: Utilidad Op - Gasto Admin"},
                {"Concepto": "(%) MARGEN REAL FINAL", "Monto": 0, "Notas": "Fórmula Excel: Utilidad Final / Ingresos"}
            ]
            df_pnl_rep = pd.DataFrame(data_pnl)

            # 5. Generar el Excel
            buffer_proy = io.BytesIO()
            with pd.ExcelWriter(buffer_proy, engine='openpyxl') as writer:
                # Hoja Principal: Estado de Resultados
                df_pnl_rep.to_excel(writer, sheet_name='Estado_Resultados', index=False)
                
                # Hoja Resumen: KPIs del Dashboard
                resumen_kpi = pd.DataFrame({
                    'Concepto': ['Ingreso Total Proyecto', 'Costo Vivo (Alerta)', 'Margen Alerta', 'Margen Real (Dashboard)'],
                    'Monto': [total_ing, costo_vivo, margen_alerta, utilidad_real]
                })
                resumen_kpi.to_excel(writer, sheet_name='Datos_Tablero', index=False)
                
                # Hojas de Detalle
                if not df_s.empty: df_s.to_excel(writer, sheet_name='Detalle_Inventario', index=False)
                if not df_c.empty: df_c.to_excel(writer, sheet_name='Compras_Pendientes', index=False)
                if not df_f.empty: df_f.to_excel(writer, sheet_name='Contabilidad_Full', index=False)
            
            st.download_button(
                f"📥 Descargar Estado de Resultados: {', '.join(proys[:1])}...", 
                data=buffer_proy.getvalue(), 
                file_name=f"Estado_Resultados_{proys[0][:10]}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            )
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
            
            
            # --- 6. ANÁLISIS DE RENTABILIDAD (NUEVO) ---
            # (Deshabilitado por solicitud del usuario)

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
        with c1: 
            st.plotly_chart(ui.config_plotly(create_improved_pie(df_c, 'Venta_Neta', 'Provincia', 'Ventas por Provincia')), use_container_width=True)
        with c2: 
            st.plotly_chart(ui.config_plotly(create_improved_pie(df_c, 'Venta_Neta', 'Zona_Comercial', 'Ventas por Zona')), use_container_width=True)
        with c3: 
            st.plotly_chart(ui.config_plotly(create_improved_pie(df_c, 'Venta_Neta', 'Categoria_Cliente', 'Ventas por Categoría')), use_container_width=True)
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

        st.divider()
        
        # --- ANÁLISIS DE RIESGO (NUEVO) ---
        st.subheader("🚨 Clientes en Riesgo (Alerta Temprana)")
        st.caption("Clientes activos que han superado en 1.5x su ciclo habitual de compra.")
        
        # 1. Calcular frecuencia por cliente
        df_risk = df_main.sort_values(['Cliente', 'invoice_date'])
        df_risk['Prev_Date'] = df_risk.groupby('Cliente')['invoice_date'].shift(1)
        df_risk['Days_Diff'] = (df_risk['invoice_date'] - df_risk['Prev_Date']).dt.days
        
        # Promedio histórico por cliente
        freq_cli = df_risk.groupby('Cliente')['Days_Diff'].mean().reset_index().rename(columns={'Days_Diff': 'Ciclo_Habitual'})
        
        # Última compra
        last_buy = df_risk.groupby('Cliente')['invoice_date'].max().reset_index().rename(columns={'invoice_date': 'Ultima_Compra'})
        
        # Unir
        df_alerta = pd.merge(freq_cli, last_buy, on='Cliente')
        df_alerta['Dias_Sin_Comprar'] = (datetime.now() - df_alerta['Ultima_Compra']).dt.days
        
        # Lógica de Riesgo: (Días > Ciclo*1.5) Y (Días < 365) [No perdidos aún] Y (Ciclo > 0)
        df_alerta['Alerta'] = (df_alerta['Dias_Sin_Comprar'] > (df_alerta['Ciclo_Habitual'] * 1.5)) & \
                              (df_alerta['Dias_Sin_Comprar'] < 365) & \
                              (df_alerta['Ciclo_Habitual'] > 0)
                              
        alertas = df_alerta[df_alerta['Alerta']].sort_values('Venta_Neta', ascending=False) if 'Venta_Neta' in df_alerta.columns else df_alerta[df_alerta['Alerta']].copy() 
        # (Nota: Venta_Neta no está en df_alerta, hay que unirla si queremos ordenar por importancia)
        
        # Traer Venta Total Histórica para ordenar
        vta_hist = df_main.groupby('Cliente')['Venta_Neta'].sum().reset_index()
        alertas = pd.merge(alertas, vta_hist, on='Cliente', how='left').sort_values('Venta_Neta', ascending=False)
        
        if not alertas.empty:
            c_r1, c_r2 = st.columns([1,3])
            with c_r1:
                ui.card_kpi("Clientes en Riesgo", len(alertas), "bg-alert-warn", formato="numero")
                
            with c_r2: 
                # Mostrar tabla simplificada
                st.dataframe(
                    alertas[['Cliente', 'Ciclo_Habitual', 'Dias_Sin_Comprar', 'Venta_Neta']].style.format({
                        'Ciclo_Habitual': '{:.0f} días',
                        'Dias_Sin_Comprar': '{:.0f} días',
                        'Venta_Neta': '₡{:,.0f}'
                    }), use_container_width=True, height=300
                )
        else:
            st.success("✅ No se detectan clientes en riesgo de fuga inminente basado en sus ciclos de compra.")

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

        st.divider()
        
        st.divider()
        
        # Filtrar productos correspondientes a las facturas del vendedor seleccionado
        if not df_v.empty and not df_prod.empty:
            ids_facturas_vendedor = df_v['id'].unique()
            df_prod_vend = df_prod[df_prod['ID_Factura'].isin(ids_facturas_vendedor)]
            
            if not df_prod_vend.empty:
                # --- SELECTOR DE MÉTRICA ---
                c_sel1, c_sel2 = st.columns([1, 3])
                with c_sel1:
                    metrica_vend = st.radio("Ver por:", ["Monto (₡)", "Cantidad (Und)", "Freq. (Docs)"], horizontal=True, label_visibility="collapsed")
                
                # Config métrica
                if "Monto" in metrica_vend: val_col, agg, fmt = 'Venta_Neta', 'sum', '.2s'
                elif "Cantidad" in metrica_vend: val_col, agg, fmt = 'quantity', 'sum', '.2s'
                else: val_col, agg, fmt = 'ID_Factura', 'nunique', ''
                
                c_top10, c_brand = st.columns(2)
                
                with c_top10:
                    st.subheader(f"🏆 Top 10 Productos ({metrica_vend})")
                    top_prods = df_prod_vend.groupby('Producto')[val_col].agg(agg).sort_values(ascending=True).tail(10).reset_index() # Sort Ascending for Horizontal Bar to put max at top? No, plotly needs max at bottom for H bar usually? Let's stick to standard logic: tail(10) gets biggest.
                    # Usually for barh, y-axis order: bottom to top. 
                    
                    fig_vp = px.bar(top_prods, x=val_col, y='Producto', orientation='h', text_auto=fmt, 
                                    title=f"Top Productos")
                    fig_vp.update_traces(marker_color='#27ae60')
                    st.plotly_chart(ui.config_plotly(fig_vp), use_container_width=True)
                
                with c_brand:
                    st.subheader(f"🥧 Mix por Marca ({metrica_vend})")
                    # Traer datos de marca desde inventario
                    df_inv = services.cargar_inventario_general()
                    if not df_inv.empty and 'Marca' in df_inv.columns:
                        df_merged_brand = pd.merge(df_prod_vend, df_inv[['ID_Producto', 'Marca']], on='ID_Producto', how='left')
                        df_merged_brand['Marca'] = df_merged_brand['Marca'].fillna("Sin Marca")
                        
                        # Preparar datos para el pie chart usando la métrica seleccionada
                        # Para count distinct (ID_Factura), groupby directo
                        df_pie_data = df_merged_brand.groupby('Marca')[val_col].agg(agg).reset_index()
                        
                        # Usar el helper
                        fig_brand = create_improved_pie(df_pie_data, val_col, 'Marca', f"Mix ({metrica_vend})")
                        st.plotly_chart(ui.config_plotly(fig_brand), use_container_width=True)
                    else:
                        st.warning("No se pudo cargar información de Marcas.")
            else:
                st.info("No hay detalle de productos disponible para este vendedor.")

# === PESTAÑA 8: RADIOGRAFÍA ===
with tab_det:
    if not df_main.empty:
        c_search, c_year = st.columns([3, 1])
        with c_search:
            cli = st.selectbox("Buscar Cliente:", sorted(df_main['Cliente'].unique()), index=None, placeholder="Escriba para buscar...")
        
        if cli:
            # Obtener años disponibles para este cliente
            df_full_history = df_main[df_main['Cliente'] == cli]
            available_years = sorted(df_full_history['invoice_date'].dt.year.unique(), reverse=True)
            
            with c_year:
                # Selector de Año (con opción 'Todos')
                rad_year = st.selectbox("Año:", ["Todos"] + available_years, key=f"rad_year_{cli}")
            
            # Filtrar datos según selección
            if rad_year == "Todos":
                df_cl = df_full_history
                is_filtered = False
            else:
                df_cl = df_full_history[df_full_history['invoice_date'].dt.year == rad_year]
                is_filtered = True

            # Cálculos KPI (Sobre la data filtrada)
            if not df_cl.empty:
                ultima = df_cl['invoice_date'].max()
                dias = (datetime.now() - ultima).days
                
                # KPI Crédito (Promedio general, no varía mucho por año pero lo recalculamos)
                dias_credito = df_cl['Dias_Credito'].mean() if 'Dias_Credito' in df_cl.columns else 0
                
                k1, k2, k3, k4, k5 = st.columns(5)
                with k1: ui.card_kpi(f"Venta {'Total' if not is_filtered else rad_year}", df_cl['Venta_Neta'].sum(), "border-green")
                with k2: ui.card_kpi("Última Compra", ultima.strftime('%d-%m-%Y'), "border-blue", formato="raw")
                with k3: ui.card_kpi("Días Inactivo", dias, "border-red" if dias>90 else "border-gray", formato="numero")
                with k4: ui.card_kpi("Días Crédito Prom.", dias_credito, "border-orange", formato="numero")
                with k5: ui.card_kpi("Ubicación", df_cl.iloc[0]['Provincia'], "border-purple", formato="raw")
                
                c_h, c_p = st.columns(2)
                with c_h:
                    st.subheader("Historial")
                    if is_filtered:
                        # Vista Mensual (Año seleccionado)
                        hist = df_cl.groupby(df_cl['invoice_date'].dt.month)['Venta_Neta'].sum().reset_index()
                        # Mapear número de mes a nombre
                        hist['Mes'] = hist['invoice_date'].map({1:'Ene',2:'Feb',3:'Mar',4:'Abr',5:'May',6:'Jun',
                                                              7:'Jul',8:'Ago',9:'Sep',10:'Oct',11:'Nov',12:'Dic'})
                        fig_h = px.bar(hist, x='Mes', y='Venta_Neta', text_auto='.2s', title=f"Ventas Mensuales {rad_year}")
                    else:
                        # Vista Anual (Historico Completo)
                        hist = df_cl.groupby(df_cl['invoice_date'].dt.year)['Venta_Neta'].sum().reset_index()
                        fig_h = px.bar(hist, x='invoice_date', y='Venta_Neta', text_auto='.2s', title="Tendencia Anual")
                        fig_h.update_xaxes(type='category') # Asegurar que años se vean como categorías
                    
                    st.plotly_chart(ui.config_plotly(fig_h), use_container_width=True)

                with c_p:
                    c_head, c_sel = st.columns([1,1])
                    with c_head: st.subheader(f"Top Productos")
                    
                    # Selector Métrica Radiografía
                    with c_sel:
                        metrica_rad = st.radio("M:", ["Monto", "Cant.", "Freq."], horizontal=True, label_visibility="collapsed", key=f"rad_met_{cli}")
                    
                    if "Monto" in metrica_rad: r_val, r_agg, r_fmt = 'Venta_Neta', 'sum', '.2s'
                    elif "Cant" in metrica_rad: r_val, r_agg, r_fmt = 'quantity', 'sum', '.2s'
                    else: r_val, r_agg, r_fmt = 'ID_Factura', 'nunique', ''

                    if not df_prod.empty:
                        # Filtrar productos usando las facturas del cliente filtrado
                        df_cp = df_prod[df_prod['ID_Factura'].isin(df_cl['id'])]
                        if not df_cp.empty:
                            top = df_cp.groupby('Producto')[r_val].agg(r_agg).sort_values(ascending=True).tail(10).reset_index()
                            st.plotly_chart(ui.config_plotly(px.bar(top, x=r_val, y='Producto', orientation='h', text_auto=r_fmt)), use_container_width=True)
                        else:
                            st.info("No hay productos para este rango.")
            else:
                 st.info(f"No hay registros de ventas para el año {rad_year}.")
                
# ... (después de mostrar los gráficos del cliente) ...              
# PREPARAR DESCARGA DEL CLIENTE
            buffer_cli = io.BytesIO()
            with pd.ExcelWriter(buffer_cli, engine='openpyxl') as writer:
                df_cl.to_excel(writer, sheet_name='Historial_Ventas', index=False)
                if not df_cp.empty:
                    df_cp.groupby('Producto')['quantity'].sum().reset_index().to_excel(writer, sheet_name='Productos_Comprados', index=False)
                        
            st.download_button(
                f"📥 Descargar Historial de {cli}",
                data=buffer_cli.getvalue(),
                file_name=f"Historial_{cli[:15]}.xlsx"
            )
# === PESTAÑA 9: CENTRO DE DESCARGAS (ACTUALIZADO) ===
with tab_down:
    st.header("📥 Centro de Descargas")
    st.markdown("Descarga aquí los datos consolidados que alimentan los gráficos de la aplicación.")
    
    col_d1, col_d2 = st.columns(2)
    
    # --- SECCIÓN 1: VENTAS Y OBJETIVOS ---
    with col_d1:
        st.subheader("📊 Ventas y Metas")
        
        # 1. Ventas Generales (Detalle Facturas)
        if not df_main.empty:
            buffer_main = ui.convert_df_to_excel(df_main[['invoice_date', 'name', 'Cliente', 'Vendedor', 'Venta_Neta', 'Provincia', 'Zona_Comercial', 'Categoria_Cliente']], "Ventas_General")
            st.download_button("📥 Histórico de Ventas (Completo)", data=buffer_main, file_name="Ventas_Generales_Alrotek.xlsx")

        # 2. Datos de Cumplimiento de Meta (Gráfico Tab 1)
        if not df_main.empty and not df_metas.empty:
            anio_actual = datetime.now().year
            v_act = df_main[df_main['invoice_date'].dt.year == anio_actual].groupby('Mes_Num')['Venta_Neta'].sum().reset_index().rename(columns={'Venta_Neta': 'Venta_Real'})
            v_meta = df_metas[df_metas['Anio'] == anio_actual].groupby('Mes_Num')['Meta'].sum().reset_index()
            df_cumplimiento = pd.DataFrame({'Mes_Num': range(1, 13)}).merge(v_act, on='Mes_Num', how='left').merge(v_meta, on='Mes_Num', how='left').fillna(0)
            df_cumplimiento['Mes'] = df_cumplimiento['Mes_Num'].map({1:'Ene',2:'Feb',3:'Mar',4:'Abr',5:'May',6:'Jun',7:'Jul',8:'Ago',9:'Sep',10:'Oct',11:'Nov',12:'Dic'})
            df_cumplimiento['Cumplimiento_Pct'] = (df_cumplimiento['Venta_Real'] / df_cumplimiento['Meta'] * 100).fillna(0)
            
            st.download_button("📥 Reporte Cumplimiento de Metas", data=ui.convert_df_to_excel(df_cumplimiento), file_name=f"Cumplimiento_Metas_{anio_actual}.xlsx")

        # 3. Datos Comparativos Anuales (Gráfico Tab 1)
        if not df_main.empty:
            anio_actual = datetime.now().year
            anio_ant = anio_actual - 1
            v_act = df_main[df_main['invoice_date'].dt.year == anio_actual].groupby('Mes_Num')['Venta_Neta'].sum().reset_index().rename(columns={'Venta_Neta': f'Venta_{anio_actual}'})
            v_ant = df_main[df_main['invoice_date'].dt.year == anio_ant].groupby('Mes_Num')['Venta_Neta'].sum().reset_index().rename(columns={'Venta_Neta': f'Venta_{anio_ant}'})
            df_comp = pd.DataFrame({'Mes_Num': range(1, 13)}).merge(v_act, on='Mes_Num', how='left').merge(v_ant, on='Mes_Num', how='left').fillna(0)
            df_comp['Diferencia'] = df_comp[f'Venta_{anio_actual}'] - df_comp[f'Venta_{anio_ant}']
            
            st.download_button(f"📥 Comparativo {anio_actual} vs {anio_ant}", data=ui.convert_df_to_excel(df_comp), file_name="Comparativo_Anual.xlsx")

    # --- SECCIÓN 2: PRODUCTOS E INVENTARIO ---
    with col_d2:
        st.subheader("📦 Productos")
        
        # 4. Mix por Tipo y Categoría (Gráficos Tab 3)
        if not df_prod.empty:
            # Agregado por Tipo (Global)
            df_p_clean = df_prod.merge(df_cat[['ID_Producto','Tipo']], on='ID_Producto', how='left').fillna({'Tipo':'Otro'})
            grp_tipo = df_p_clean.groupby('Tipo')['Venta_Neta'].sum().reset_index()
            
            # Agregado por Vendedor y Producto (Top Vendedores)
            df_top_vend = pd.merge(df_p_clean, df_main[['id', 'Vendedor']], left_on='ID_Factura', right_on='id', how='left')
            grp_vend_prod = df_top_vend.groupby(['Vendedor', 'Producto'])['Venta_Neta'].sum().reset_index()

            # Usamos un ExcelWriter para bajar varias hojas en un solo archivo
            buffer_prod = io.BytesIO()
            with pd.ExcelWriter(buffer_prod, engine='openpyxl') as writer:
                df_prod.to_excel(writer, sheet_name='Detalle_Movimientos', index=False)
                grp_tipo.to_excel(writer, sheet_name='Mix_por_Tipo', index=False)
                grp_vend_prod.to_excel(writer, sheet_name='Top_Producto_Vendedor', index=False)
            
            st.download_button("📥 Reporte Maestro de Productos (Multi-Hoja)", data=buffer_prod.getvalue(), file_name="Maestro_Productos.xlsx")
        
        # 5. Inventario Baja Rotación
        if st.button("🔄 Generar Baja Rotación"):
            df_inv_dl, _ = services.cargar_inventario_baja_rotacion()
            if not df_inv_dl.empty:
                st.download_button("📥 Descargar Baja Rotación", data=ui.convert_df_to_excel(df_inv_dl), file_name="Baja_Rotacion.xlsx")

    st.divider()
    col_d3, col_d4 = st.columns(2)

    # --- SECCIÓN 3: CARTERA Y RIESGO ---
    with col_d3:
        st.subheader("💰 Cartera y Riesgo")
        
        # 6. Cartera y Antigüedad (Gráfico Tab 5)
        df_cx_dl = services.cargar_cartera()
        if not df_cx_dl.empty:
            # Resumen por Antigüedad
            res_ant = df_cx_dl.groupby('Antiguedad')['amount_residual'].sum().reset_index()
            
            buffer_cx = io.BytesIO()
            with pd.ExcelWriter(buffer_cx, engine='openpyxl') as writer:
                df_cx_dl.to_excel(writer, sheet_name='Detalle_Facturas', index=False)
                res_ant.to_excel(writer, sheet_name='Resumen_Antiguedad', index=False)
                
            st.download_button("📥 Reporte Cartera y Antigüedad", data=buffer_cx.getvalue(), file_name="Reporte_Cartera.xlsx")

        # 7. Clientes en Riesgo (Alerta Tab 6)
        if not df_main.empty:
            # Recalcular lógica de riesgo
            df_risk = df_main.sort_values(['Cliente', 'invoice_date'])
            df_risk['Prev_Date'] = df_risk.groupby('Cliente')['invoice_date'].shift(1)
            df_risk['Days_Diff'] = (df_risk['invoice_date'] - df_risk['Prev_Date']).dt.days
            freq_cli = df_risk.groupby('Cliente')['Days_Diff'].mean().reset_index().rename(columns={'Days_Diff': 'Ciclo_Habitual'})
            last_buy = df_risk.groupby('Cliente')['invoice_date'].max().reset_index().rename(columns={'invoice_date': 'Ultima_Compra'})
            df_alerta = pd.merge(freq_cli, last_buy, on='Cliente')
            df_alerta['Dias_Sin_Comprar'] = (datetime.now() - df_alerta['Ultima_Compra']).dt.days
            df_alerta['Alerta'] = (df_alerta['Dias_Sin_Comprar'] > (df_alerta['Ciclo_Habitual'] * 1.5)) & (df_alerta['Dias_Sin_Comprar'] < 365)
            riesgo_dl = df_alerta[df_alerta['Alerta']].copy()
            
            if not riesgo_dl.empty:
                st.download_button("📥 Clientes en Riesgo (Alerta Fuga)", data=ui.convert_df_to_excel(riesgo_dl), file_name="Clientes_En_Riesgo.xlsx")

    # --- SECCIÓN 4: VENDEDORES ---
    with col_d4:
        st.subheader("👤 Performance")
        if not df_main.empty:
            perf = df_main.groupby(['Vendedor', df_main['invoice_date'].dt.year])['Venta_Neta'].sum().reset_index()
            st.download_button("📥 Ventas por Vendedor (Anual)", data=ui.convert_df_to_excel(perf), file_name="Performance_Vendedores.xlsx")








