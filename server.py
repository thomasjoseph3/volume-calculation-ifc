import ifcopenshell
import ifcopenshell.geom
from flask import Flask, request, jsonify
from OCC.Core.GProp import GProp_GProps
from OCC.Core.BRepGProp import brepgprop

app = Flask(__name__)

# Load the IFC file
ifc_file = ifcopenshell.open('institute.ifc')

# Initialize the geometry settings (needed to compute areas and volumes)
settings = ifcopenshell.geom.settings()
settings.set(settings.USE_PYTHON_OPENCASCADE, True)

# Function to get material assignments for an element
def get_material(element):
    if hasattr(element, 'HasAssociations'):
        for rel in element.HasAssociations:
            if rel.is_a("IfcRelAssociatesMaterial"):
                material = rel.RelatingMaterial
                
                # Check if the material is part of a layer set
                if material.is_a("IfcMaterialLayerSetUsage"):
                    return material.ForLayerSet.MaterialLayers
                
                # Check if the material is a list of materials
                elif material.is_a("IfcMaterialList"):
                    return material.Materials
                
                # Check if the material is a single IfcMaterial
                elif material.is_a("IfcMaterial"):
                    return [material]  # Return as a list to unify processing
    
    return None

# Function to get direct material assignment, if any
def get_direct_material(element):
    if hasattr(element, 'HasAssociations'):
        for rel in element.HasAssociations:
            if rel.is_a("IfcRelAssociatesMaterial"):
                material = rel.RelatingMaterial
                if material.is_a("IfcMaterial"):
                    return material
    return None

# Function to get material layers and their total thickness
def get_material_layers_and_thickness(element):
    total_thickness = 0
    layer_materials = []
    
    if hasattr(element, 'HasAssociations'):
        for rel in element.HasAssociations:
            if rel.is_a("IfcRelAssociatesMaterial"):
                material = rel.RelatingMaterial
                
                # Check if the material is part of a layer set
                if material.is_a("IfcMaterialLayerSetUsage"):
                    for layer in material.ForLayerSet.MaterialLayers:
                        if hasattr(layer, 'LayerThickness'):
                            total_thickness += layer.LayerThickness
                            layer_materials.append((layer.Material.Name, layer.LayerThickness))
    
    return layer_materials, total_thickness

# Function to calculate the geometry-based volume of an element with maximum accuracy
def calculate_element_volume(element):
    try:
        shape = ifcopenshell.geom.create_shape(settings, element)
        
        # Calculate volume with maximum accuracy
        props = GProp_GProps()
        brepgprop.VolumeProperties(shape.geometry, props)
        return props.Mass()
    
    except Exception as e:
        print(f"Failed to compute geometry for element {element.Name}: {e}")
        return 0.0

# Function to calculate the area of an element
def calculate_element_area(element):
    try:
        shape = ifcopenshell.geom.create_shape(settings, element)
        
        # Calculate area with maximum accuracy
        props = GProp_GProps()
        brepgprop.SurfaceProperties(shape.geometry, props)
        return props.Mass()
    
    except Exception as e:
        print(f"Failed to compute area for element {element.Name}: {e}")
        return 0.0

# Function to retrieve all elements that use the specified material
def retrieve_elements_by_material(ifc_file, material_name):
    total_material_volume = 0.0
    element_count = 0
    elements_entirely_made_of_material = 0
    elements_using_material_in_layers = 0
    elements_list = []
    
    for element in ifc_file.by_type("IfcElement"):
        materials = get_material(element)
        direct_material = get_direct_material(element)
        
        element_info = {
            "Name": element.Name,
            "GlobalId": element.GlobalId,
            "MaterialLayers": [],
            "EntirelyMadeOf": None,
            "BaseMaterial": None
        }

        if materials:
            if any(material.is_a("IfcMaterialLayer") for material in materials):
                # Material Layers exist
                layer_materials, total_thickness = get_material_layers_and_thickness(element)
                if any(material_name.lower() in mat_name.lower() for mat_name, _ in layer_materials):
                    element_info["MaterialLayers"] = layer_materials
                    element_info["TotalThickness"] = total_thickness
                    # Calculate the material volume
                    area = calculate_element_area(element)
                    material_volume = area * total_thickness
                    total_material_volume += material_volume
                    element_count += 1  # Increment the count of elements
                    elements_using_material_in_layers += 1  # Increment count for elements using material in layers
            
            # Handle elements made entirely of a single material
            if direct_material and direct_material.Name.lower() == material_name.lower():
                element_info["EntirelyMadeOf"] = direct_material.Name
                element_volume = calculate_element_volume(element)
                total_material_volume += element_volume
                element_count += 1  # Increment the count of elements
                elements_entirely_made_of_material += 1  # Increment count for elements entirely made of the material

        if element_info["MaterialLayers"] or element_info["EntirelyMadeOf"]:
            elements_list.append(element_info)

    return {
        "total_elements": element_count,
        "elements_entirely_made_of_material": elements_entirely_made_of_material,
        "elements_using_material_in_layers": elements_using_material_in_layers,
        "total_material_volume": total_material_volume,
        "elements": elements_list
    }

# Route to handle material query
@app.route('/material', methods=['GET'])
def get_material_data():
    material_name = request.args.get('material_name')
    if not material_name:
        return jsonify({"error": "Please provide a material_name parameter"}), 400
    
    result = retrieve_elements_by_material(ifc_file, material_name)
    return jsonify(result)

# Main entry point
if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)
