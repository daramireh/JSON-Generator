import pandas as pd
import json
import openai
import os
import re
from flask import Flask, request, jsonify, send_file, render_template
from jsonschema import validate
from jsonschema.exceptions import ValidationError

# Configurar la API de OpenAI
openai.api_key = os.getenv("OPENAI_KEY")

# Función para validar el JSON contra el esquema
def validate_json(data, schema):
    try:
        validate(instance=data, schema=schema)
    except ValidationError as err:
        return False, str(err)
    return True, None

# Función para convertir el Excel a un formato para enviar a la API de OpenAI
def excel_to_data(file_path):
    xls = pd.ExcelFile(file_path)
    sections = []
    for sheet_name in xls.sheet_names:
        df = pd.read_excel(file_path, sheet_name=sheet_name)
        
        # Convertir los objetos Timestamp a cadenas de texto
        for column in df.select_dtypes(['datetime64']).columns:
            df[column] = df[column].astype(str)
        
        fields = [{"fName": col, "caption": col} for col in df.columns]
        section = {
            "Name": sheet_name,
            "Header": True,
            "USePosition": True,
            "Fields": fields
        }
        sections.append(section)
    
    data = {
        "signature": os.path.basename(file_path).split('.')[0],
        "type": "Excel",
        "Sections": sections
    }
    
    return data

# Función para generar JSON usando la API de OpenAI
def generate_json_with_openai(data):
    prompt_schema = {
        "signature": "aquí escribes el nombre del archivo",
        "type": "Aquí escribes el tipo del archivo",
        "Sections": [
            {
                "Name": "nombre de la hoja del archivo",
                "Header": True,
                "USePosition": True,
                "Fields": [
                    {
                        "fName": "Aquí escribes el nombre del encabezado de cada columna",
                        "caption": "Aquí escribes el nombre del archivo"
                    }
                ]
            }
        ]
    }

    prompt = (
        f"Genera un JSON válido según el siguiente esquema: {json.dumps(prompt_schema, ensure_ascii=False)} "
        f"con estos datos: {json.dumps(data, ensure_ascii=False)}. "
        "Asegúrate de incluir todas las propiedades requeridas, especialmente 'Sections', y evita propiedades adicionales. "
        "El valor de 'type' debe ser 'Excel'."
    )
    
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "Eres un asistente útil."},
            {"role": "user", "content": prompt}
        ]
    )
    response_text = response['choices'][0]['message']['content'].strip()
    
    # Utilizar expresión regular para extraer el contenido JSON
    json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
    if json_match:
        json_str = json_match.group(0)
        try:
            generated_json = json.loads(json_str)
        except json.JSONDecodeError as e:
            print(f"Error decoding JSON: {e}")
            print(f"Extracted JSON string was: {json_str}")
            return None

        return generated_json
    else:
        print("No JSON found in response text.")
        print(f"Response text was: {response_text}")
        return None

# Inicializar la aplicación Flask
app = Flask(__name__)

# Crear el directorio temporal si no existe
UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Ruta para servir el formulario HTML
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return "No file part"
    
    file = request.files['file']
    
    if file.filename == '':
        return "No selected file"
    
    if file:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
        file.save(file_path)
        
        # Convertir el archivo Excel a datos
        data = excel_to_data(file_path)
        
        # Generar JSON usando la API de OpenAI
        generated_json = generate_json_with_openai(data)
        
        if generated_json is None:
            return "Error generating JSON from OpenAI response."
        
        # Validar el JSON
        #is_valid, validation_error = validate_json(generated_json, json_schema)
        #if not is_valid:
        #    return f"JSON Validation Error: {validation_error}"
        
        # Guardar el JSON en un archivo
        json_file_path = os.path.join(app.config['UPLOAD_FOLDER'], 'output.json')
        with open(json_file_path, 'w', encoding='utf-8') as json_file:
            json.dump(generated_json, json_file, indent=4, ensure_ascii=False)
        
        return send_file(json_file_path, as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True)
