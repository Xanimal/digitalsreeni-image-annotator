
import json
import os
import yaml
from PIL import Image

from PyQt5.QtCore import QRectF
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QMessageBox, QFileDialog

import os
import json
from PyQt5.QtWidgets import QMessageBox

def import_coco_json(file_path, class_mapping):
    with open(file_path, 'r') as f:
        coco_data = json.load(f)

    imported_annotations = {}
    image_info = {}

    # Create reverse mapping of category IDs to names
    category_id_to_name = {cat['id']: cat['name'] for cat in coco_data['categories']}

    # Determine the image directory
    json_dir = os.path.dirname(file_path)
    images_dir = os.path.join(json_dir, 'images')
    
    if not os.path.exists(images_dir):
        print(f"Warning: 'images' subdirectory not found at {images_dir}")

    for image in coco_data['images']:
        file_name = image['file_name']
        image_path = os.path.join(images_dir, file_name)
        
        image_info[image['id']] = {
            'file_name': file_name,
            'width': image['width'],
            'height': image['height'],
            'path': image_path,
            'id': image['id']
        }
        
        if not os.path.isfile(image_path):
            print(f"Image not found: {file_name}")

    for ann in coco_data['annotations']:
        image_id = ann['image_id']
        if image_id not in image_info:
            print(f"Warning: Annotation refers to non-existent image ID: {image_id}")
            continue

        file_name = image_info[image_id]['file_name']
        category_name = category_id_to_name[ann['category_id']]

        if file_name not in imported_annotations:
            imported_annotations[file_name] = {}

        if category_name not in imported_annotations[file_name]:
            imported_annotations[file_name][category_name] = []

        annotation = {
            'category_id': ann['category_id'],
            'category_name': category_name
        }

        if 'segmentation' in ann:
            seg = ann['segmentation']
            if type(seg) is dict and "counts" in seg:
                annotation["segmentation"] = seg
                annotation['type'] = 'rle'
            else:
                annotation['segmentation'] = seg[0]
                annotation['type'] = 'polygon'
        elif 'bbox' in ann:
            annotation['bbox'] = ann['bbox']
            annotation['type'] = 'rectangle'

        imported_annotations[file_name][category_name].append(annotation)

    return imported_annotations, image_info


def import_yolo_v8(yaml_file_path, class_mapping):
    if not os.path.exists(yaml_file_path):
        raise ValueError("The selected YAML file does not exist.")
    
    directory_path = os.path.dirname(yaml_file_path)
    
    with open(yaml_file_path, 'r') as f:
        yaml_data = yaml.safe_load(f)
    
    class_names = yaml_data.get('names', [])
    if not class_names:
        raise ValueError("No class names found in the YAML file.")
    
    train_dir = os.path.join(directory_path, 'train')
    if not os.path.exists(train_dir):
        raise ValueError("No 'train' subdirectory found in the YAML file's directory.")
    
    imported_annotations = {}
    image_info = {}
    
    images_dir = os.path.join(train_dir, 'images')
    labels_dir = os.path.join(train_dir, 'labels')
    
    if not os.path.exists(images_dir) or not os.path.exists(labels_dir):
        raise ValueError("The 'train' directory must contain both 'images' and 'labels' subdirectories.")
    
    missing_images = []
    missing_labels = []
    
    for label_file in os.listdir(labels_dir):
        if label_file.lower().endswith('.txt'):
            base_name = os.path.splitext(label_file)[0]
            img_file = None
            img_path = None
            
            # Check for various image formats
            for ext in ['.jpg', '.jpeg', '.png', '.tiff', '.bmp', '.gif']:
                potential_img_file = base_name + ext
                potential_img_path = os.path.join(images_dir, potential_img_file)
                if os.path.exists(potential_img_path):
                    img_file = potential_img_file
                    img_path = potential_img_path
                    break
            
            if img_path is None:
                missing_images.append(base_name)
                continue
            
            with Image.open(img_path) as img:
                img_width, img_height = img.size
            
            image_id = len(image_info) + 1
            image_info[image_id] = {
                'file_name': img_file,
                'width': img_width,
                'height': img_height,
                'id': image_id,
                'path': img_path
            }
            
            imported_annotations[img_file] = {}
            
            label_path = os.path.join(labels_dir, label_file)
            with open(label_path, 'r') as f:
                lines = f.readlines()
            
            for line in lines:
                parts = line.strip().split()
                if len(parts) >= 5:
                    class_id = int(parts[0])
                    if class_id >= len(class_names):
                        print(f"Warning: Class ID {class_id} in {label_file} is out of range. Skipping this annotation.")
                        continue
                    class_name = class_names[class_id]
                    
                    if class_name not in imported_annotations[img_file]:
                        imported_annotations[img_file][class_name] = []
                    
                    if len(parts) == 5:  # bounding box format
                        x_center, y_center, width, height = map(float, parts[1:5])
                        x1 = (x_center - width/2) * img_width
                        y1 = (y_center - height/2) * img_height
                        x2 = (x_center + width/2) * img_width
                        y2 = (y_center + height/2) * img_height
                        
                        annotation = {
                            'category_id': class_id,
                            'category_name': class_name,
                            'type': 'rectangle',
                            'bbox': [x1, y1, x2-x1, y2-y1]
                        }
                    else:  # polygon format
                        polygon = [float(coord) * (img_width if i % 2 == 0 else img_height) for i, coord in enumerate(parts[1:])]
                        
                        annotation = {
                            'category_id': class_id,
                            'category_name': class_name,
                            'type': 'polygon',
                            'segmentation': polygon
                        }
                    
                    imported_annotations[img_file][class_name].append(annotation)
    
    # Check for images without labels
    for img_file in os.listdir(images_dir):
        base_name, ext = os.path.splitext(img_file)
        if ext.lower() in ['.jpg', '.jpeg', '.png', '.tiff', '.bmp', '.gif']:
            label_file = base_name + '.txt'
            if not os.path.exists(os.path.join(labels_dir, label_file)):
                missing_labels.append(img_file)
    
    if missing_images or missing_labels:
        message = "The following issues were found:\n\n"
        if missing_images:
            message += f"Labels without corresponding images: {', '.join(missing_images)}\n\n"
        if missing_labels:
            message += f"Images without corresponding labels: {', '.join(missing_labels)}\n\n"
        message += "Do you want to continue importing the remaining data?"
        
        reply = QMessageBox.question(None, "Import Issues", message, 
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        
        if reply == QMessageBox.No:
            raise ValueError("Import cancelled due to missing files.")
    
    return imported_annotations, image_info

def process_import_format(import_format, file_path, class_mapping):
    if import_format == "COCO JSON":
        return import_coco_json(file_path, class_mapping)
    elif import_format == "YOLO v8":
        return import_yolo_v8(file_path, class_mapping)
    else:
        raise ValueError(f"Unsupported import format: {import_format}")


