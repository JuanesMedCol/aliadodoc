import streamlit as st
import google.generativeai as genai
from PIL import Image
import io
import os

# --- Configuración de la Página ---
st.set_page_config(
    page_title="AliadoDoc",
    page_icon="🧠",
    layout="wide"
)

# --- SISTEMA DE CONDUCTA (TU GEM) ---
# 🚨 PEGA TU PROMPT COMPLETO DE CONDUCTA AQUÍ 🚨
SISTEMA_DE_CONDUCTA = os.environ.get("GEM_PROMPT", 'aaa')

# --- Barra Lateral para Configuración ---
with st.sidebar:
    
    st.title("AliadoDoc")
    st.header("⚙️ Configuración")
    
    # 1. Cargar API Key desde Colab Secrets
    api_key = os.environ.get("GEMINI_API_KEY", 'aaa')     
    
    
    model_option = st.selectbox(
        "Selecciona el Modelo",
        ("gemini-2.5-pro", "gemini-2.5-flash")
    )
 
# --- Funciones Auxiliares ---
def get_gemini_response(api_key, model_name, user_prompt, system_instruction, content_files=None):
    """Función para interactuar con la API de Gemini."""
    # En un entorno real (no Colab con variables de entorno), esto fallaría,
    if not api_key:
        return "⚠️ Por favor, asegúrate de que la variable GEMINI_API_KEY esté configurada."
    
    try:
        genai.configure(api_key=api_key)
        
        # Inicializar el modelo con la instrucción de sistema
        model = genai.GenerativeModel(
            model_name=model_name,
            system_instruction=system_instruction
        )
        
        generation_parts = [user_prompt]
        if content_files:
            for file in content_files:
                generation_parts.append(file)
        
        # Generar respuesta (stream=True para efecto de escritura)
        response = model.generate_content(generation_parts, stream=True)
        return response
    except Exception as e:
        return f"❌ Error: {str(e)}"

def process_uploaded_file(uploaded_file):
    """Procesa el archivo subido y lo convierte al formato que Gemini entiende."""
    if uploaded_file is None: return None
    mime_type = uploaded_file.type
    
    # Si es imagen
    if mime_type.startswith('image'):
        try:
            # Usamos read() y BytesIO para que PIL pueda abrir el archivo sin guardarlo en disco
            return Image.open(io.BytesIO(uploaded_file.read()))
        except: 
            st.error("Error al procesar la imagen. Asegúrese de que el formato es válido.")
            return None
            
    # Si es texto (txt, py, md, csv, etc.)
    elif mime_type.startswith('text') or mime_type == 'application/json':
        try:
            # Volvemos al inicio del buffer antes de leer
            uploaded_file.seek(0)
            return uploaded_file.read().decode("utf-8")
        except: 
            st.error("Error al leer el archivo de texto.")
            return None
            
    return None

# --- Interfaz Principal ---

# Inicializar sesión para gestión de archivos
if 'uploaded_file_data' not in st.session_state:
    st.session_state.uploaded_file_data = None
if 'uploaded_file_name' not in st.session_state:
    st.session_state.uploaded_file_name = None
# Inicializar variable para prompt generado por botón
if 'prompt_from_button' not in st.session_state:
    st.session_state.prompt_from_button = None


# --- Obtener contenido de la sesión para usar y mostrar ---
processed_content = st.session_state.uploaded_file_data
file_name_to_display = st.session_state.uploaded_file_name

# Mostrar la previsualización del contenido guardado en la sesión
if processed_content:
    st.subheader(f"Archivo en Sesión: {file_name_to_display}")
    
    # Mostrar preview
    if isinstance(processed_content, Image.Image):
        st.image(processed_content, caption="Imagen cargada", width=300)
    else:
        st.text_area("Previsualización:", value=processed_content, height=100)
    
    # Botón para limpiar la subida de sesión
    if st.button("🗑️ Eliminar archivo de la sesión"):
        st.session_state.uploaded_file_data = None
        st.session_state.uploaded_file_name = None
        # Forzar la recarga para que el file_uploader se resetee visualmente
        st.rerun() 

# =================================================================
# BLOQUE DE CARGA DE ARCHIVOS (MOVIMIENTO HACIA ARRIBA)
# =================================================================
with st.expander("📂 Cargar Archivos (Imágenes o Texto)", expanded=True):
    # Usar un widget file_uploader para permitir la selección de archivos.
    # El archivo subido aquí espera una acción para ser guardado en la sesión.
    current_uploaded_file = st.file_uploader(
        "Arrastra tu archivo aquí (Pulsa 'Guardar' para enviarlo a la sesión de chat)", 
        type=["jpg", "png", "txt", "csv", "py", "md"], 
        # Clave única para evitar errores de widget si el estado cambia
        key="file_uploader_widget"
    )
    
    # Lógica de botón: Solo guardar si hay un archivo seleccionado y se pulsa el botón.
    if current_uploaded_file is not None:
        if st.button("💾 Guardar Archivo en Sesión", key="save_file_btn"):
            # Lógica de persistencia: Guarda el archivo subido
            
            # Chequea si es un nuevo archivo (o si queremos re-procesar el mismo)
            if st.session_state.uploaded_file_name != current_uploaded_file.name:
                st.session_state.uploaded_file_name = current_uploaded_file.name
            
            # Es crucial volver al inicio del buffer antes de leer
            current_uploaded_file.seek(0)
            
            # Guardamos el archivo procesado en la sesión
            st.session_state.uploaded_file_data = process_uploaded_file(current_uploaded_file)
            st.toast(f"Archivo '{current_uploaded_file.name}' cargado a la sesión. ¡Listo para chatear!", icon='💾')
            # Forzamos un rerun para que el preview superior se actualice inmediatamente.
            st.rerun()
            

# =================================================================
# FIN DEL BLOQUE DE CARGA DE ARCHIVOS
# =================================================================

# --- BOTONES DE ACCIONES RÁPIDAS (NUEVA SECCIÓN) ---
st.markdown("---")
st.subheader("🚀 Acciones Rápidas")
col1, col2 = st.columns(2)

# Botón 1: Asesoría Rápida (Iniciar Proyecto)
if col1.button("🧠 Asesoría Rápida (Iniciar Proyecto)", use_container_width=True):
    # Almacena el prompt para ser procesado inmediatamente después del rerun
    st.session_state.prompt_from_button = "Desearia ver ejemplos"
    st.rerun() # Fuerza la re-ejecución del script para entrar en la lógica del chat

# Botón 2: Descargar Formatos Esenciales
format_content = """
# Plantillas y Formatos de Proyecto

Aquí tienes enlaces a formatos esenciales que podrías necesitar:

Tipo de documento (instructivo, guía o procedimiento)
Título del documento
Objetivo
Alcance
Contexto o proceso asociado
Actividades o pasos
Responsables
Registros o evidencias
Indicaciones de formato institucional

---
*Nota: En una aplicación real, estos serían enlaces directos de descarga.*
"""
col2.download_button(
    label="⬇️ Descargar Formatos Esenciales",
    data=format_content,
    file_name="Formatos_Esenciales_AliadoDoc.md",
    mime="text/markdown",
    use_container_width=True
)
st.markdown("---")

# Inicializar historial de chat en session_state si no existe
if "messages" not in st.session_state:
    # Mensaje inicial del asistente (la "gem" de bienvenida)
    st.session_state.messages = [{
        "role": "assistant",
        "content": "¡Hola! Soy AliadoDoc. Puedes subir una imagen o archivo de texto para que lo analice, o usar los botones de 'Acciones Rápidas' para comenzar."
    }]

# Mostrar mensajes anteriores
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])


# --- Lógica de Chat Unificada ---
# 1. Obtener prompt del botón (si existe) y limpiarlo del estado de sesión.
prompt_from_button = st.session_state.pop('prompt_from_button', None)
# 2. Obtener prompt del input de chat.
prompt_from_chat = st.chat_input("Escribe tu mensaje...")

# Determinar el prompt final a usar
user_prompt = prompt_from_button or prompt_from_chat

if user_prompt:
    # Agregar el mensaje del usuario al historial
    st.session_state.messages.append({"role": "user", "content": user_prompt})
    with st.chat_message("user"):
        st.markdown(user_prompt)

    if not api_key:
        st.warning("⚠️ Necesitas una API Key. Por favor, configura el Secreto de Colab llamado GEMINI_API_KEY.")
    else:
        with st.chat_message("assistant"):
            msg_placeholder = st.empty()
            full_response = ""
            
            # Si hay contenido en la sesión, se adjunta a la llamada a la API
            content_list = []
            if processed_content: content_list.append(processed_content)
            
            # Llamada a la API, pasando la instrucción del sistema y el prompt
            response_stream = get_gemini_response(api_key, model_option, user_prompt, SISTEMA_DE_CONDUCTA, content_list)
            
            if isinstance(response_stream, str):
                msg_placeholder.markdown(response_stream)
                full_response = response_stream
            else:
                try:
                    for chunk in response_stream:
                        if chunk.text:
                            full_response += chunk.text
                            # Muestra la respuesta en tiempo real
                            msg_placeholder.markdown(full_response + "▌")
                    msg_placeholder.markdown(full_response)
                except Exception as e:
                    st.error(f"Error: {e}")
            
            st.session_state.messages.append({"role": "assistant", "content": full_response})