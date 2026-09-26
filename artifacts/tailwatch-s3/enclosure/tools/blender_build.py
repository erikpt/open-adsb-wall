#!/usr/bin/env python3
"""Build tailwatch_enclosure.blend (+ preview renders + web GLB) from the
positioned STLs in enclosure/blender_import/ (see tools/export_blender_stls.sh
to regenerate those from the OpenSCAD source of truth).

Run headless:
    blender --background --python tools/blender_build.py

Requires Blender's Python to have `numpy` (needed by the glTF exporter addon);
if it errors on "No module named 'numpy'", find Blender's python (bpy report
via `blender --background --python-expr "import sys; print(sys.executable)"`)
and `<that-python> -m pip install --break-system-packages numpy`.
"""
import bpy, os, math, mathutils

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMPORT_DIR = os.path.join(BASE, "blender_import")
OUT_BLEND = os.path.join(BASE, "tailwatch_enclosure.blend")
PREVIEW_DIR = os.path.join(BASE, "preview")

# --- clean default scene ---
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
for block in list(bpy.data.meshes):
    bpy.data.meshes.remove(block)
for block in list(bpy.data.materials):
    bpy.data.materials.remove(block)

# name -> (stl filename, color RGBA, is_reference_dummy)
PARTS = [
    ("frame_left",   "frame_left.stl",   (0.85, 0.85, 0.88, 1.0), False),
    ("frame_right",  "frame_right.stl",  (0.70, 0.70, 0.75, 1.0), False),
    ("portal_pod",   "portal_pod.stl",   (0.55, 0.75, 0.95, 1.0), False),
    ("button_rods",  "button_rods.stl",  (0.95, 0.75, 0.20, 1.0), False),
    ("strap_1",      "strap_1.stl",      (0.40, 0.80, 0.45, 1.0), False),
    ("strap_2",      "strap_2.stl",      (0.40, 0.80, 0.45, 1.0), False),
    ("bowtie_key_1", "bowtie_key_1.stl", (1.00, 0.388, 0.278, 1.0), False),
    ("bowtie_key_2", "bowtie_key_2.stl", (1.00, 0.388, 0.278, 1.0), False),
    ("panel_dummy",  "panel_dummy.stl",  (0.12, 0.12, 0.14, 1.0), True),
    ("portal_dummy", "portal_dummy.stl", (0.05, 0.35, 0.15, 1.0), True),
]

def make_material(name, rgba):
    mat = bpy.data.materials.new(name=f"mat_{name}")
    mat.use_nodes = True
    mat.diffuse_color = rgba
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = rgba
        if "Roughness" in bsdf.inputs:
            bsdf.inputs["Roughness"].default_value = 0.65
        for spec_key in ("Specular IOR Level", "Specular"):
            if spec_key in bsdf.inputs:
                bsdf.inputs[spec_key].default_value = 0.25
    return mat

objects = []
for name, fname, rgba, is_dummy in PARTS:
    path = os.path.join(IMPORT_DIR, fname)
    bpy.ops.wm.stl_import(filepath=path)
    obj = bpy.context.selected_objects[-1]
    obj.name = name
    obj.data.name = f"{name}_mesh"
    mat = make_material(name, rgba)
    obj.data.materials.clear()
    obj.data.materials.append(mat)
    if is_dummy:
        obj.hide_render = False  # keep visible for context, but tag it
        obj.pass_index = 99
    objects.append(obj)

# shade smooth-ish is unnecessary for hard-surface printed parts; keep flat.

# --- world / light setup ---
world = bpy.data.worlds.new("World")
bpy.context.scene.world = world
world.use_nodes = True
bg = world.node_tree.nodes.get("Background")
if bg:
    bg.inputs[0].default_value = (0.05, 0.05, 0.06, 1.0)
    bg.inputs[1].default_value = 0.6

def add_sun(name, rot, energy=3.0):
    light_data = bpy.data.lights.new(name=name, type='SUN')
    light_data.energy = energy
    light_obj = bpy.data.objects.new(name=name, object_data=light_data)
    bpy.context.collection.objects.link(light_obj)
    light_obj.rotation_euler = rot
    return light_obj

add_sun("Key", (math.radians(55), 0, math.radians(35)), energy=3.5)
add_sun("Fill", (math.radians(75), 0, math.radians(-120)), energy=1.5)
add_sun("Rim",  (math.radians(110), 0, math.radians(200)), energy=2.0)

# --- render engine: Eevee (reliable headless in this container) ---
scene = bpy.context.scene
try:
    scene.render.engine = 'BLENDER_EEVEE_NEXT'
except TypeError:
    scene.render.engine = 'BLENDER_EEVEE'
scene.render.resolution_x = 1600
scene.render.resolution_y = 1200
scene.render.image_settings.file_format = 'PNG'
scene.render.film_transparent = False

# --- camera ---
cam_data = bpy.data.cameras.new("Camera")
cam_data.lens = 50
cam_obj = bpy.data.objects.new("Camera", cam_data)
bpy.context.collection.objects.link(cam_obj)
scene.camera = cam_obj

# Coordinate system (matches params.scad "back view"): X = width (0..256),
# Y = height (0..128), Z = DEPTH (LED face at z=0, wall-mount flange at z~34.5).
# So "front" (LED face, what a viewer in the room sees) looks along -Z -> +Z;
# "back" (wall side / open cavity) looks along +Z -> -Z.
target = mathutils.Vector((128, 64, 17))

def point_camera(cam, location, target):
    cam.location = location
    direction = target - mathutils.Vector(location)
    rot_quat = direction.to_track_quat('-Z', 'Y')
    cam.rotation_euler = rot_quat.to_euler()

VIEWS = {
    "front": (60, -30, -480),   # LED face, slight 3/4 offset, pulled back to frame full outline
    "iso":   (470, -400, 300),  # 3/4 iso angle showing the open assembly clearly
    "back":  (170, 90, 460),    # wall / open-cavity side, slight 3/4 offset
}

os.makedirs(PREVIEW_DIR, exist_ok=True)
for view, loc in VIEWS.items():
    point_camera(cam_obj, loc, target)
    scene.render.filepath = os.path.join(PREVIEW_DIR, f"blender_{view}.png")
    bpy.ops.render.render(write_still=True)
    print(f"rendered {view} -> {scene.render.filepath}")

# --- save .blend ---
bpy.ops.wm.save_as_mainfile(filepath=OUT_BLEND)
print("saved", OUT_BLEND)

# --- export combined glTF/GLB for the web (model-viewer) ---
WEB_DIR = os.path.join(BASE, "web")
os.makedirs(WEB_DIR, exist_ok=True)
GLB_PATH = os.path.join(WEB_DIR, "tailwatch_enclosure.glb")
bpy.ops.object.select_all(action='DESELECT')
for obj in objects:
    obj.select_set(True)
bpy.ops.export_scene.gltf(
    filepath=GLB_PATH,
    export_format='GLB',
    use_selection=True,
    export_apply=True,
    export_materials='EXPORT',
    export_yup=True,
)
print("exported glb", GLB_PATH, os.path.getsize(GLB_PATH), "bytes")
