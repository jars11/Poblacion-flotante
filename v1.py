import os, re, subprocess, time, csv
import threading, tempfile, sys
import keyboard
import time
from datetime import datetime, date
import tkinter as tk
from tkinter import messagebox, ttk
from google.cloud import documentai
from openai import OpenAI
from tkcalendar import DateEntry
from dotenv import load_dotenv

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm

load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise ValueError("No se encontró OPENAI_API_KEY en el archivo .env")
client = OpenAI(api_key=api_key)

NAPS2_DIR = os.path.dirname(os.path.abspath(__file__))
NAPS2_EXE = os.path.join(NAPS2_DIR, "NAPS2.Console.exe")
CSV_FILE = os.path.join(
    os.path.expanduser(r"~"),
    "OneDrive",
    "Escritorio",
    f"Poblacion Flotante {date.today().strftime('%d-%m-%Y')}.csv"
)
OPENAI_MODEL = "gpt-4o"
TMP_DIR = tempfile.gettempdir()

# Ruta fija a SumatraPDF
SUMATRA_EXE = r"C:\Users\cityh\AppData\Local\SumatraPDF\SumatraPDF.exe"

# --------- Utilidades previas ---------
def siguiente_nombre(base_dir, fecha):
    i = 0
    exts = [".jpg", ".JPG", ".jpeg", ".JPEG"]
    while True:
        fname = f"{fecha}.jpg" if i == 0 else f"{fecha} ({i}).jpg"
        path = os.path.join(base_dir, fname)
        if not any(os.path.exists(os.path.splitext(path)[0] + ext) for ext in exts):
            return path
        i += 1

def file_ready(p):
    if not os.path.exists(p): return False
    try:
        sz = os.path.getsize(p)
        with open(p,'rb'): pass
        return sz > 0
    except PermissionError:
        return False

def extraer_campo(texto, palabra_clave):
    patron = rf"{re.escape(palabra_clave)}.*\n(?:.*\n)*?(\b[A-ZÁÉÍÓÚÜÑ]+(?:[^A-Za-z]+[A-ZÁÉÍÓÚÜÑ]+)*\b[^\n]*)"
    m = re.search(patron, texto, re.MULTILINE)
    return m.group(1).strip() if m else ""

def _buscar_desde_clave(texto, palabra_clave):
    m = re.search(re.escape(palabra_clave), texto, flags=re.IGNORECASE)
    return texto[m.end():] if m else ""

def extraer_fecha(texto, palabra_clave):
    bloque = _buscar_desde_clave(texto, palabra_clave)
    pat = re.compile(r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})")
    for linea in bloque.splitlines():
        s = linea.strip()
        if not s: continue
        m = pat.search(s)
        if m:
            fecha = m.group(1)
            for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%d-%m-%y"):
                try:
                    dt = datetime.strptime(fecha, fmt)
                    return dt.strftime("%d-%m-%Y")
                except ValueError:
                    pass
            return fecha.replace("/", "-")
    return ""

def extraer_numero_identidad(texto):
    patron = r"\b\d{1}\.\d{3}\.\d{3}-\d{1}\b"
    m = re.search(patron, texto)
    return m.group(0) if m else ""

def inferir_sexo(nombres):
    prompt = (f"Dado el siguiente nombre completo: '{nombres}', "
              "responde únicamente con 'M' si es masculino o 'F' si es femenino. "
              "No escribas nada más.")
    kwargs = {"model": OPENAI_MODEL, "messages": [{"role": "user", "content": prompt}], "temperature": 0, "max_completion_tokens": 1}
    resp = client.chat.completions.create(**kwargs)
    s = (resp.choices[0].message.content or "").strip().upper()
    if s.startswith("M"): return "M"
    if s.startswith("F"): return "F"
    return ""

# --------- Ficha PDF ---------
def _nombre_completo(d):
    return " ".join(x for x in [d.get("nombre1",""), d.get("nombre2",""),
                                d.get("apellido1",""), d.get("apellido2","")] if x).strip()

def _fmt_fecha(fecha_dd_mm_aaaa:str):
    return fecha_dd_mm_aaaa.replace("-", "/") if fecha_dd_mm_aaaa else ""

def generar_ficha_pdf_A4(destino_pdf, habitacion, checkin, checkout, titular, acomp):
    """
    A4, márgenes 5mm. Ajustes: anchos más cómodos en 'Nacionalidad/Ciudad/Teléfono',
    bajar 'Importes cobrados' para que no se pise con 'Vehículo', y mejor alineado.
    """
    c = canvas.Canvas(destino_pdf, pagesize=A4)
    W, H = A4
    m = 15*mm
    y = H - m

    inner_w_mm = (W/mm - 2*m/mm)

    def txt(x, y, s, size=9, bold=False):
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        c.drawString(x, y, s)

    def caja(x, y, w, h):
        c.rect(x, y, w, h, stroke=1, fill=0)

    # Encabezado
    txt(m, y-1, "City Hotel", 16, True)
    txt(W-50*mm-m, y-1, "Nro. Habitación:", 9, True)
    caja(W-25*mm-m, y-3, 25*mm, 10)
    txt(W-14*mm-m, y-1, habitacion or "", 10)
    y -= 14*mm

    # Check in/out
    txt(m, y, "Check in", 9, True); caja(m+22*mm, y-2, 28*mm, 10)
    txt(m+54*mm, y, "Check in hora: " + datetime.now().strftime("%H:%M"), 9)
    y -= 9*mm
    txt(m, y, "Check out", 9, True); caja(m+22*mm, y-2, 28*mm, 10)
    txt(m+54*mm, y, "Check out hora:", 9)
    txt(m+24*mm, y+9*mm-1, _fmt_fecha(checkin), 8)
    txt(m+24*mm, y-1, _fmt_fecha(checkout), 8)
    y -= 10*mm

    # Titular
    txt(m, y, "Datos de los huéspedes", 9, True)
    y -= 5*mm
    caja(m, y-25*mm, W-2*m, 24*mm)
    txt(m+2*mm, y-1, "Titular de la reserva", 8)
    caja(m+2*mm, y-10*mm, W-2*m-4*mm, 8*mm)
    txt(m+4*mm, y-8*mm, _nombre_completo(titular), 9)

    suby = y-20*mm
    # Nuevos anchos más cómodos (en mm)
    # Nacionalidad 35, Ciudad 35, Teléfono 30, F.Nac 24, Documento resto
    nx = [0*(W-2*m)/5, 1*(W-2*m)/5, 2*(W-2*m)/5, 3*(W-2*m)/5, 4*(W-2*m)/5]  # mm desde m
    widths = [(W-2*m)/5, (W-2*m)/5, (W-2*m)/5, (W-2*m)/5, (W-2*m)/5]  # último calculado
    labels = ["Nacionalidad", "Ciudad", "Teléfono", "F. Nac.", "Documento Número y Tipo"]
    for i, lab in enumerate(labels):
        xx = m + nx[i]; ww = widths[i]
        txt(xx, suby+8*mm, lab, 7); caja(xx, suby, ww, 7*mm)
    txt(m+2*mm, suby+2, titular.get("idpaisnacionalidad",""), 8)
    txt(m+ (nx[1]+2), suby+2, titular.get("lugarNacimiento",""), 8)
    txt(m+ (nx[3]+2), suby+2, _fmt_fecha(titular.get("fechaNacimiento","")), 8)
    doc = f'{titular.get("documento","")} {titular.get("tipodocumento","") or "CI"}'.strip()
    txt(m+ (nx[4]+2), suby+2, doc, 8)

    y = y - 26*mm - 6*mm

    # Acompañantes (4 filas)
    txt(m, y, "Acompañantes", 9, True); y -= 5*mm
    fila_h = 10*mm
    cant_acomp = 4 # máximo 4 acompañantes
    alto = cant_acomp*fila_h; caja(m, y-alto, W-2*m, alto)
    # Encabezados
    headers = [("Nombre y Apellido", 0), ("F. Nac.", 95*mm), ("Documento Número y Tipo", 123*mm)]
    for lab, xmm in headers:
        txt(m + xmm + 2, y+1*mm, lab, 8)
    for i in range(cant_acomp):
        yy = y - (i+1)*fila_h
        c.line(m + 95*mm, yy, m + 95*mm, yy+fila_h)
        c.line(m + 123*mm, yy, m + 123*mm, yy+fila_h)
        c.line(m, yy, W-m, yy)
        if i < len(acomp):
            d = acomp[i]
            txt(m+2, yy+2, _nombre_completo(d), 8.5)
            txt(m+97*mm, yy+2, _fmt_fecha(d.get("fechaNacimiento","")), 8.5)
            doca = f'{d.get("documento","")} {d.get("tipodocumento","") or "CI"}'.strip()
            txt(m+125*mm, yy+2, doca, 8.5)

    y = y - alto - 7*mm

    # Reserva realizada desde
    txt(m, y, "Reserva realizada desde", 9, True); y -= 4*mm
    caja(m, y-10*mm, W-2*m, 10*mm)
    txt(m+2*mm, y-8, "Booking      Despegar      Directo con hotel      Otros (indicar)", 8)

    y -= 15*mm

    # Datos tarjeta y vehículo (ligeramente más altos)
    txt(m, y, "Datos de la tarjeta de crédito", 9, True)
    txt(W/2, y, "Datos del vehículo", 9, True)
    y -= 3*mm
    caja(m, y-28*mm, (W-2*m)/2-2*mm, 28*mm)
    caja(W/2+2*mm, y-28*mm, (W-2*m)/2-2*mm, 28*mm)

    # Información adicional
    info_y = y - 30*mm
    info_h = 60*mm
    caja(m, info_y - info_h, W - 2*m, info_h)

    # Texto de estacionamiento
    estacionamiento_texto = (
        "ESTACIONAMIENTO\n"
        "LA EMPRESA PERMITE EL USO GRATUITO DEL ESTACIONAMIENTO DEL HOTEL, \n"
        "PERO NO ASUME OBLIGACIÓN DE ESPECIE ALGUNA REFERIDA A LOS VEHÍCULOS Y/O EFECTOS \n"
        "QUE PUDIERAN DEJARSE DENTRO DE LOS MISMOS -QUE SEAN ESTACIONADOS EN ESOS ESPACIOS, \n"
        "NI ASUME OBLIGACIÓN ALGUNA DE VIGILANCIA, CUSTODIA NI SIMILAR."
    )
    for i, line in enumerate(estacionamiento_texto.split("\n")):
        txt(m + 2 * mm, info_y - 5 * mm - (i * 10), line, 7)

    # Texto de niños
    ninos_texto = (
        "NIÑOS\n"
        "La empresa no asume obligación de especie alguna de cuidado ni de vigilancia de niños, \n"
        "los cuales deberán ser cuidados y vigilados por sus respectivos padres o responsables \n"
        "y bajo su exclusiva responsabilidad y deben ser acompañados en todas las instalaciones del hotel."
    )
    for i, line in enumerate(ninos_texto.split("\n")):
        txt(m + 2 * mm, info_y - 25 * mm - (i * 10), line, 7)

    # Política de cancelación
    cancelacion_texto = (
        "POLÍTICA DE CANCELACIÓN\n"
        "Si su reserva está realizada directamente con nuestro hotel y se retira antes de lo acordado, \n"
        "deberá abonar todo lo adeudado por concepto de alojamiento y gastos de consumo, más el resto de la reserva contratada.\n"
        "Si su reserva está realizada por medio de portales electrónicos, se tomará la política de cancelación del portal con el cual usted contrató."
    )
    for i, line in enumerate(cancelacion_texto.split("\n")):
        txt(m + 2 * mm, info_y - 45 * mm - (i * 10), line, 7)

    # --- Sección inferior: 'Tarifa por noche / Seña' a la izquierda y 'Importes cobrados' a la derecha ---
    bottom_h = 20*mm
    imp_w = 70*mm
    gap = 2*mm
    left_w = (W-2*m) - (imp_w + gap)
    base_y = m + 10*mm

    caja(m, base_y, left_w, bottom_h)
    txt(m+2*mm, base_y + bottom_h - 10, "Tarifa por noche                      Seña", 8)

    imp_x = m + left_w + gap
    caja(imp_x, base_y, imp_w, bottom_h)
    txt(imp_x + 2*mm, base_y + bottom_h - 10, "IMPORTES COBRADOS", 8, True)
    txt(imp_x + 2*mm, base_y + bottom_h - 20, "Alojamiento", 8)
    txt(imp_x + 2*mm, base_y + bottom_h - 30, "Otros consumos", 8)
    txt(imp_x + 2*mm, base_y + bottom_h - 40, "Total", 8)

    c.line(W - m - 40*mm, m - 5*mm, W - m, m - 5*mm)
    txt(W - m - 25*mm, m - 10*mm, "Firma", 8)

    c.showPage(); c.save()

def imprimir_pdf_sumatra(path_pdf):
    if not os.path.isfile(SUMATRA_EXE):
        raise FileNotFoundError(f"No se encontró el ejecutable de Sumatra en:\n{SUMATRA_EXE}")
    cmd = [SUMATRA_EXE, "-silent", "-exit-on-print", "-print-settings", "paper=A4,portrait", "-print-to-default", path_pdf]
    subprocess.run(cmd, check=False)


# --------- GUI ---------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        keyboard.add_hotkey('ctrl+q', self.ingresar_datos_titular_facturacion)
        self.title("Registro de huéspedes")
        self.geometry("960x540"); self.minsize(900, 500)

        self.habitacion = tk.StringVar()
        self.fecha_salida = tk.StringVar()
        self.huespedes = []

        frm = tk.Frame(self); frm.pack(pady=10)
        tk.Label(frm, text="Número de habitación:").grid(row=0, column=0, sticky="e", padx=(0,6))
        tk.Entry(frm, textvariable=self.habitacion, width=12).grid(row=0, column=1, sticky="w")
        tk.Label(frm, text="Fecha de salida:").grid(row=1, column=0, sticky="e", padx=(0,6))

        try:
            today = date.today()
            self.calendario = DateEntry(frm, date_pattern="dd-mm-yyyy",
                                        year=today.year, month=today.month, day=today.day, width=12)
            self.calendario.grid(row=1, column=1, sticky="w")
            self.fecha_salida.set(today.strftime("%d-%m-%Y"))
            def actualizar_fecha(*_):
                d = self.calendario.get_date()
                self.fecha_salida.set(d.strftime("%d-%m-%Y"))
            self.calendario.bind("<<DateEntrySelected>>", actualizar_fecha)
        except ImportError:
            tk.Entry(frm, textvariable=self.fecha_salida, width=12).grid(row=1, column=1, sticky="w")

        tk.Button(frm, text="Escanear cédula(s)", command=self.agregar_huesped).grid(row=2, column=0, columnspan=2, pady=10)

        cols = ("Habitación", "Fecha de salida", "Nombre(s)", "Apellido(s)", "Documento")
        self.tree = ttk.Treeview(self, columns=cols, show="headings")
        for c, w in zip(cols, (100, 130, 220, 220, 180)):
            self.tree.heading(c, text=c); self.tree.column(c, width=w, anchor="w")
        hsb = ttk.Scrollbar(self, orient="horizontal", command=self.tree.xview)
        self.tree.configure(xscrollcommand=hsb.set)
        self.tree.pack(expand=True, fill="both", padx=10, pady=(10, 0)); hsb.pack(fill="x", padx=10, pady=(0, 10))

        btn_row = tk.Frame(self); btn_row.pack(pady=6)
        tk.Button(btn_row, text="Eliminar huésped", command=self.eliminar_huesped).pack(side="left", padx=6)
        tk.Button(btn_row, text="Exportar CSV", command=self.exportar_csv).pack(side="left", padx=6)
        tk.Button(btn_row, text="Imprimir ficha", command=self.imprimir_ficha).pack(side="left", padx=6)

    # --- Acciones auxiliares ---
    def ingresar_datos_titular_facturacion(self, event=None):
        keyboard.press_and_release('tab')
        keyboard.press_and_release('tab')
        keyboard.press_and_release('c')
        keyboard.press_and_release('tab')
        if self.huespedes:
            titular = self.huespedes[0]
            keyboard.write(titular.get("documento", ""))
            keyboard.press_and_release('tab')
            nombre_completo = " ".join([
                titular.get("nombre1", ""),
                titular.get("nombre2", ""),
                titular.get("apellido1", ""),
                titular.get("apellido2", "")
            ]).strip()
            keyboard.write(nombre_completo)
        keyboard.press_and_release('enter')

    def eliminar_huesped(self):
        item = self.tree.selection()
        if not item:
            messagebox.showwarning("Aviso", "Seleccione un huésped para eliminar."); return
        idx = self.tree.index(item)
        if idx >= len(self.huespedes): return
        datos = self.huespedes[idx]
        self.tree.delete(item); del self.huespedes[idx]
        if os.path.exists(CSV_FILE):
            with open(CSV_FILE, "r", encoding="utf-8") as f:
                filas = list(csv.DictReader(f, delimiter=';'))
            filas = [row for row in filas if not (row.get("documento") == datos["documento"]
                                                  and row.get("habitacion") == datos["habitacion"])]
            with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=datos.keys(), delimiter=';')
                writer.writeheader(); writer.writerows(filas)

    def exportar_csv(self):
        if not os.path.exists(CSV_FILE):
            messagebox.showwarning("Aviso", "No hay datos para exportar."); return
        with open(CSV_FILE, "r", encoding="utf-8") as f:
            filas = f.readlines()
        if not filas:
            messagebox.showwarning("Aviso", "No hay datos para exportar."); return
        header = filas[0].strip().lower()
        if "habitacion" in header and "documento" in header: filas = filas[1:]
        if not filas:
            messagebox.showwarning("Aviso", "No hay datos para exportar después de quitar el header."); return
        with open(CSV_FILE, "w", encoding="utf-8") as f:
            f.writelines(filas)

    # --- OCR/Scan & parse ---
    def _procesar_imagen(self, destino):
        if not os.path.exists(destino):
            messagebox.showerror("Error", "El archivo escaneado no se generó correctamente."); return
        PROJECT_ID = "newagent-mjbv"; LOCATION = "us"; PROCESSOR_ID = "16226d3ac97c18b5"
        client_docai = documentai.DocumentProcessorServiceClient()
        name = client_docai.processor_path(PROJECT_ID, LOCATION, PROCESSOR_ID)
        with open(destino, "rb") as f: content = f.read()
        raw_document = documentai.RawDocument(content=content, mime_type="image/jpeg")
        request = documentai.ProcessRequest(name=name, raw_document=raw_document)
        result = client_docai.process_document(request=request)
        texto = result.document.text

        print(texto)  # DEBUG

        bloques_texto = re.split(r"(?=REP[ÚU]BLICA)", texto, flags=re.IGNORECASE)
        bloques_texto = [b for b in bloques_texto if b.strip()]

        for b in bloques_texto:
            apellidos = extraer_campo(b, "Apellido")
            nombres = extraer_campo(b, "Nombre")
            fecha_nac = extraer_fecha(b, "Nacimiento")
            numero_doc = extraer_numero_identidad(b).replace(".", "").replace("-", "")
            nacionalidad = extraer_campo(b, "Nacionalidad")
            if nacionalidad.strip().upper() == "URUGUAYA": nacionalidad = "UY"
            elif nacionalidad.strip().upper() == "ARGENTINA": nacionalidad = "AR"
            lugar_nac = extraer_campo(b, "Lugar")
            if "/" in lugar_nac:
                lugar_nac = lugar_nac.split("/", 1)[0].strip()
            idpaisdocumento = nacionalidad
            idpaisnacionalidad = nacionalidad
            idpaisresidencia = nacionalidad
            tipodocumento = "CI"

            # Separar apellidos considerando apellidos compuestos y palabras en minúsculas
            apellidos_split = []
            palabras = apellidos.split()
            apellido_actual = []
            for palabra in palabras:
                apellido_actual.append(palabra)
                if palabra.isupper():
                    apellidos_split.append(" ".join(apellido_actual))
                    apellido_actual = []
            if apellido_actual:
                apellidos_split.append(" ".join(apellido_actual))
            apellido1 = apellidos_split[0] if len(apellidos_split) > 0 else ""
            apellido2 = apellidos_split[1] if len(apellidos_split) > 1 else ""
            nombres_split = nombres.split()
            nombre1 = nombres_split[0] if len(nombres_split) > 0 else ""
            nombre2 = nombres_split[1] if len(nombres_split) > 1 else ""

            sexo = inferir_sexo(nombres)

            fechaEntrada = date.today().strftime("%d-%m-%Y")
            fechaSalida = self.fecha_salida.get()
            habitacion = self.habitacion.get()

            datos = {
                "documento": numero_doc,
                "idpaisdocumento": idpaisdocumento,
                "tipodocumento": tipodocumento,
                "apellido1": apellido1,
                "apellido2": apellido2,
                "nombre1": nombre1,
                "nombre2": nombre2,
                "sexo": sexo,
                "idpaisnacionalidad": idpaisnacionalidad,
                "lugarNacimiento": lugar_nac,
                "idpaisresidencia": idpaisresidencia,
                "fechaNacimiento": fecha_nac,
                "fechaEntrada": fechaEntrada,
                "fechaSalida": fechaSalida,
                "habitacion": habitacion
            }

            datos_csv = datos.copy()
            datos_csv.pop("lugarNacimiento", None)
            with open(CSV_FILE, "a", newline="", encoding="utf-8") as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=datos_csv.keys(), delimiter=';')
                if csvfile.tell() == 0: writer.writeheader()
                writer.writerow(datos_csv)

            self.huespedes.append(datos)
            self.tree.insert("", "end",
                             values=(habitacion, fechaSalida, f"{nombre1} {nombre2}", f"{apellido1} {apellido2}", numero_doc))

        if not bloques_texto:
            messagebox.showwarning("Aviso", "No se detectaron cédulas en la imagen.")

    def _wait_for_file(self, destino, t0, timeout=180):
        if file_ready(destino):
            self._procesar_imagen(destino); return
        if time.time()-t0 > timeout:
            messagebox.showerror("Error", "El archivo escaneado no se generó a tiempo."); return
        self.after(500, self._wait_for_file, destino, t0, timeout)

    def escanear_async(self, destino):
        def run():
            subprocess.run([NAPS2_EXE, "scan", "--output", destino, "--force"],
                           check=False, shell=False, cwd=NAPS2_DIR)
        threading.Thread(target=run, daemon=True).start()
        self._wait_for_file(destino, time.time())

    def agregar_huesped(self):
        if not self.habitacion.get() or not self.fecha_salida.get():
            messagebox.showerror("Error", "Debe ingresar número de habitación y fecha de salida.")
            return
        try:
            fecha_salida_dt = datetime.strptime(self.fecha_salida.get(), "%d-%m-%Y").date()
        except Exception:
            messagebox.showerror("Error", "La fecha de salida no tiene el formato correcto (dd-mm-aaaa).")
            return
        if fecha_salida_dt <= date.today():
            messagebox.showerror("Error", "La fecha de salida debe ser posterior a hoy.")
            return
        fecha = date.today().strftime("%Y%m%d")
        destino = siguiente_nombre(TMP_DIR, fecha)
        self.escanear_async(destino)

    def imprimir_ficha(self):
        hab = self.habitacion.get().strip()
        if not hab:
            messagebox.showerror("Error", "Ingrese el número de habitación.")
            return
        grupo = [h for h in self.huespedes if (h.get("habitacion","") == hab)]
        if not grupo:
            messagebox.showwarning("Aviso", "No hay huéspedes con esa habitación.")
            return
        titular = grupo[0]; acomp = grupo[1:5]
        checkin = titular.get("fechaEntrada",""); checkout = self.fecha_salida.get()

        fd, path_pdf = tempfile.mkstemp(prefix="ficha_", suffix=".pdf"); os.close(fd)
        try:
            generar_ficha_pdf_A4(path_pdf, hab, checkin, checkout, titular, acomp)
            imprimir_pdf_sumatra(path_pdf)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo imprimir la ficha:\n{e}")

if __name__ == "__main__":
    app = App()
    app.mainloop()
