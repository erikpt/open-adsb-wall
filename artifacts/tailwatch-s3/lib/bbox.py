import math


def box(lat, lon, nm=10):
    """nm miles in each direction → OpenSky lamin/lomin/lamax/lomax."""
    dlat = nm / 69.0
    dlon = nm / (69.0 * max(0.2, math.cos(math.radians(lat))))
    return {
        "lamin": lat - dlat,
        "lamax": lat + dlat,
        "lomin": lon - dlon,
        "lomax": lon + dlon,
    }
