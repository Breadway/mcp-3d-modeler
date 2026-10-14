import cadquery as cq

# --- Parameters (mm) ---
# Phone body: 164.17 x 78 x 7.8 mm (per user-supplied CMF Phone 2 Pro dimension
# diagram; refines the 164 x 78 x 7.8 mm GSMArena/Wikipedia figure used in v1).
# Camera-bump protrusion still isn't given anywhere, so the cradle continues to
# grip the phone by its perimeter only, with the back/camera area left open
# over a window -- correct regardless of exact bump height or position.
phone_l, phone_w, phone_t = 164.17, 78.0, 7.8
corner_r = 9.0          # estimated phone corner radius (still not given in the diagrams; conservative guess)
clear_h = 0.6           # total horizontal clearance around the phone (both sides combined)
clear_v = 0.4           # vertical clearance above the phone's back before the lip layer
wall = 3.0              # side wall thickness around the phone cavity
floor_t = 2.5           # bottom frame thickness (has the camera-clearance window cut into it)
lip_t = 1.8             # top retention-lip layer thickness
lip_overlap = 1.8       # how far the lip overhangs onto the phone's front face (snap-fit amount)
frame_margin = 9.0      # inset of the camera-clearance window from the phone's edges

# --- CMF "Accessory Point" anti-rotation feature ---
# The supplied diagram shows a real, dedicated M2.5 accessory-mount screw under
# a 19.3mm cover disc, positioned near the bottom-right of the phone's back
# (bottom-left chassis screw is ~15mm from that corner per the diagram's own
# dimension chain). Reading exact X/Y off a 2D diagram is inherently imprecise,
# so this is a BEST-EFFORT estimate, not a measured value:
#   - along the long axis (X here): ~67mm from center, towards the end
#     opposite the camera cluster (i.e. near the bottom edge)
#   - along the short axis (Y here): ~24mm from center, towards one side
# VERIFY against the physical phone before drilling/screwing -- that's exactly
# why the port below is a generously oversized clearance hole (10mm) in a wide
# solid pad (16mm), not a tight M2.5 clearance hole: it tolerates this position
# estimate being off by several mm. Once you've confirmed true center, either
# redrill a precise ~2.8mm M2.5-clearance hole through the pad, or just bridge
# the oversized hole with a fender washer under the screw head.
ap_offset_x = -67.0
ap_offset_y = 24.0
ap_pad_dia = 16.0
ap_hole_dia = 10.0

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

# Solid pad under the Accessory Point location, guaranteeing material there
# even though the estimated position falls near/inside the window's edge
ap_pad = (
    cq.Workplane("XY", origin=(ap_offset_x, ap_offset_y, 0))
    .circle(ap_pad_dia / 2)
    .extrude(floor_t)
)
floor_layer = floor_layer.union(ap_pad)

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

# Oversized clearance port through the pad for the Accessory Point screw
ap_hole = (
    cq.Workplane("XY", origin=(ap_offset_x, ap_offset_y, -1))
    .circle(ap_hole_dia / 2)
    .extrude(floor_t + 2)
)
result = result.cut(ap_hole).clean()
