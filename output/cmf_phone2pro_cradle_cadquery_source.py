import cadquery as cq

# --- Parameters (mm) ---
# Phone body: 164 x 78 x 7.8 mm (GSMArena / Wikipedia spec for CMF Phone 2 Pro).
# Camera-bump protrusion isn't published, so this cradle grips the phone by its
# perimeter only -- the whole back/camera area is left open over a window, so
# it's correct regardless of exact bump height or position.
phone_l, phone_w, phone_t = 164.0, 78.0, 7.8
corner_r = 9.0          # estimated phone corner radius (not published; conservative guess)
clear_h = 0.6           # total horizontal clearance around the phone (both sides combined)
clear_v = 0.4           # vertical clearance above the phone's back before the lip layer
wall = 3.0              # side wall thickness around the phone cavity
floor_t = 2.5           # bottom frame thickness (has the camera-clearance window cut into it)
lip_t = 1.8             # top retention-lip layer thickness
lip_overlap = 1.8       # how far the lip overhangs onto the phone's front face (snap-fit amount)
frame_margin = 9.0      # inset of the camera-clearance window from the phone's edges

cavity_l, cavity_w = phone_l + clear_h, phone_w + clear_h
outer_l, outer_w = cavity_l + 2 * wall, cavity_w + 2 * wall
lip_l, lip_w = cavity_l - 2 * lip_overlap, cavity_w - 2 * lip_overlap
window_l, window_w = cavity_l - 2 * frame_margin, cavity_w - 2 * frame_margin
outer_r = corner_r + wall

z_floor = floor_t
z_cavity_top = floor_t + phone_t + clear_v
z_top = z_cavity_top + lip_t

# Layer A: floor frame with the camera-clearance window cut all the way through
floor_layer = (
    cq.Workplane("XY")
    .rect(outer_l, outer_w).extrude(floor_t)
    .edges("|Z").fillet(outer_r)
    .faces(">Z").workplane()
    .rect(window_l, window_w).cutBlind(-floor_t)
)

# Layer B: side walls forming the phone cavity -- phone's sides are hugged all
# the way around, back is open (aligned with the window in Layer A)
wall_layer = (
    cq.Workplane("XY", origin=(0, 0, z_floor))
    .rect(outer_l, outer_w).extrude(phone_t + clear_v)
    .edges("|Z").fillet(outer_r)
    .faces(">Z").workplane()
    .rect(cavity_l, cavity_w).cutBlind(-(phone_t + clear_v))
)

# Layer C: snap-fit retention lip, overhangs the phone's front face on all 4 sides
lip_layer = (
    cq.Workplane("XY", origin=(0, 0, z_cavity_top))
    .rect(outer_l, outer_w).extrude(lip_t)
    .edges("|Z").fillet(outer_r)
    .faces(">Z").workplane()
    .rect(lip_l, lip_w).cutBlind(-lip_t)
)

result = floor_layer.union(wall_layer).union(lip_layer).clean()
