from flask import Flask, render_template, request, jsonify, send_file
import os
import base64
from PIL import Image
import io
import numpy as np
from werkzeug.utils import secure_filename
import uuid

app = Flask(__name__)

# Configuration
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# Create upload folder
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg', 'bmp'}

def image_to_base64(image_path):
    with open(image_path, "rb") as image_file:
        encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
        return f"data:image/png;base64,{encoded_string}"

def encode_image(cover_array, secret_array):
    """
    Encode secret image into cover image using LSB
    """
    cover_height, cover_width = cover_array.shape[0], cover_array.shape[1]
    secret_height, secret_width = secret_array.shape[0], secret_array.shape[1]
    
    if secret_height > cover_height or secret_width > cover_width:
        raise ValueError("Secret image must be smaller than cover image")
    
    # Create a copy of cover image
    encoded_array = cover_array.copy()
    
    # For each pixel in the secret image
    for i in range(secret_height):
        for j in range(secret_width):
            # Get the RGB values of secret pixel
            r, g, b = secret_array[i, j]
            
            # Store the MSB of each color channel in the LSB of cover image
            # This way we can recover the original colors later
            encoded_array[i, j, 0] = (cover_array[i, j, 0] & 0xFE) | ((r >> 7) & 1)
            encoded_array[i, j, 1] = (cover_array[i, j, 1] & 0xFE) | ((g >> 7) & 1)
            encoded_array[i, j, 2] = (cover_array[i, j, 2] & 0xFE) | ((b >> 7) & 1)
    
    return encoded_array

def decode_image(encoded_array):
    """
    Extract hidden image from encoded array
    """
    height, width = encoded_array.shape[0], encoded_array.shape[1]
    
    # Create array for secret image
    secret_array = np.zeros((height, width, 3), dtype=np.uint8)
    
    # Extract LSB from each pixel and reconstruct the MSB
    for i in range(height):
        for j in range(width):
            # Extract the LSB and shift to MSB position (multiply by 128)
            # This gives us either 0 or 128 for each channel
            r_bit = (encoded_array[i, j, 0] & 1) * 255
            g_bit = (encoded_array[i, j, 1] & 1) * 255
            b_bit = (encoded_array[i, j, 2] & 1) * 255
            
            # Assign to secret array
            secret_array[i, j, 0] = r_bit
            secret_array[i, j, 1] = g_bit
            secret_array[i, j, 2] = b_bit
    
    return secret_array

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/hide', methods=['POST'])
def hide_image():
    try:
        # Check if files were uploaded
        if 'cover_image' not in request.files or 'secret_image' not in request.files:
            return jsonify({'error': 'Both images are required'}), 400
        
        cover_file = request.files['cover_image']
        secret_file = request.files['secret_image']
        
        if cover_file.filename == '' or secret_file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        # Generate unique filenames
        cover_id = str(uuid.uuid4())
        secret_id = str(uuid.uuid4())
        cover_path = os.path.join(app.config['UPLOAD_FOLDER'], f'{cover_id}.png')
        secret_path = os.path.join(app.config['UPLOAD_FOLDER'], f'{secret_id}.png')
        output_path = os.path.join(app.config['UPLOAD_FOLDER'], f'encoded_{cover_id}.png')
        
        # Open and convert images to RGB
        cover_img = Image.open(cover_file).convert('RGB')
        secret_img = Image.open(secret_file).convert('RGB')
        
        # Resize secret image if it's larger than cover
        if secret_img.size[0] > cover_img.size[0] or secret_img.size[1] > cover_img.size[1]:
            # Resize secret image to fit in cover
            ratio = min(cover_img.size[0] / secret_img.size[0], cover_img.size[1] / secret_img.size[1])
            new_size = (int(secret_img.size[0] * ratio), int(secret_img.size[1] * ratio))
            secret_img = secret_img.resize(new_size, Image.Resampling.LANCZOS)
        
        # Save as PNG
        cover_img.save(cover_path, 'PNG')
        secret_img.save(secret_path, 'PNG')
        
        # Convert to numpy arrays
        cover_array = np.array(cover_img)
        secret_array = np.array(secret_img)
        
        # Encode the secret image into cover
        encoded_array = encode_image(cover_array, secret_array)
        encoded_image = Image.fromarray(encoded_array)
        encoded_image.save(output_path, 'PNG')
        
        # Convert to base64 for preview
        encoded_base64 = image_to_base64(output_path)
        
        return jsonify({
            'success': True,
            'encoded_image': encoded_base64,
            'message': 'Image hidden successfully!'
        })
        
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': f'An error occurred: {str(e)}'}), 500

@app.route('/extract', methods=['POST'])
def extract_image():
    try:
        if 'encoded_image' not in request.files:
            return jsonify({'error': 'Encoded image is required'}), 400
        
        encoded_file = request.files['encoded_image']
        
        if encoded_file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        # Generate unique filename
        encoded_id = str(uuid.uuid4())
        encoded_path = os.path.join(app.config['UPLOAD_FOLDER'], f'{encoded_id}.png')
        extracted_path = os.path.join(app.config['UPLOAD_FOLDER'], f'extracted_{encoded_id}.png')
        
        # Open and convert to RGB
        encoded_img = Image.open(encoded_file).convert('RGB')
        encoded_img.save(encoded_path, 'PNG')
        
        # Convert to numpy array
        encoded_array = np.array(encoded_img)
        
        # Decode the hidden image
        secret_array = decode_image(encoded_array)
        secret_image = Image.fromarray(secret_array)
        secret_image.save(extracted_path, 'PNG')
        
        # Convert to base64 for preview
        extracted_base64 = image_to_base64(extracted_path)
        
        return jsonify({
            'success': True,
            'extracted_image': extracted_base64,
            'message': 'Hidden image extracted successfully!'
        })
        
    except Exception as e:
        return jsonify({'error': f'An error occurred: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
    