# Población Flotante

Automatiza el registro de huéspedes y la carga de datos de **población flotante** hacia el sistema del Ministerio del Interior, orientado a hoteles (desarrollado y usado para **City Hotel**).

## Descripción

Esta aplicación de escritorio facilita el proceso de check-in de huéspedes mediante:

- Escaneo de cédulas de identidad (frente y dorso)
- Extracción automática de datos mediante OCR (Google Document AI + OpenAI GPT-4o)
- Gestión de titular y acompañantes
- Generación e impresión de fichas de registro en PDF (formato A4)
- Exportación de los datos a CSV listo para la carga en el sistema de Población Flotante del Ministerio del Interior

## Características principales

- Interfaz gráfica simple con Tkinter
- Escaneo de documentos con **NAPS2**
- Extracción inteligente de:
  - Nombres y apellidos
  - Número de documento (formato uruguayo)
  - Fecha de nacimiento
  - Nacionalidad / lugar de nacimiento
  - Inferencia de sexo
- Generación de ficha de huésped personalizada
- Impresión automática con **SumatraPDF**
- Exportación diaria a CSV (`Poblacion Flotante DD-MM-YYYY.csv`)

## Requisitos

### Software necesario
- Python 3.10 o superior
- [NAPS2](https://www.naps2.com/) (incluido o en la misma carpeta del script)
- [SumatraPDF](https://www.sumatrapdfreader.org/) (ruta configurable)
- Cuenta de OpenAI con API Key
- Proyecto de Google Cloud con Document AI habilitado (opcional según configuración)

### Dependencias de Python
```bash
pip install openai google-cloud-documentai python-dotenv tkcalendar reportlab keyboard
