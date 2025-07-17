from bbos.registry import all_types

import numpy as np
from itertools import chain

_C_TYPES = {
    np.dtype('float32').type: "float",
    np.dtype('float64').type: "double",
    np.dtype('int32').type: "int32_t",
    np.dtype('uint32').type: "uint32_t",
    np.dtype('int16').type: "int16_t",
    np.dtype('uint16').type: "uint16_t",
    np.dtype('int8').type: "int8_t",
    np.dtype('uint8').type: "uint8_t",
    np.dtype('bool').type: "bool",
}


def _to_fields(obj):
    """
    Accepts:
      • list with elements of any of these shapes:
          (name, dtype)
          (name, (dtype, n))
          (name, dtype, shape)
      • NumPy dtype
    Yields (name, base_dtype, shape_tuple)
    """
    if isinstance(obj, np.dtype):
        for name, fmt, shape in obj.descr:
            base = np.dtype(fmt).type
            shape = tuple(shape) if shape else ()
            yield name, base, shape
        return

    for entry in obj:
        if len(entry) == 2:
            name, spec = entry
            if isinstance(spec, tuple) and len(spec) == 2 and isinstance(
                    spec[1], int):
                base, n = spec
                yield name, base, (n, )
            else:
                yield name, spec, ()
        elif len(entry) == 3:
            name, base, shape = entry
            shape = tuple(shape) if isinstance(shape,
                                               (list, tuple)) else (shape, )
            yield name, base, shape
        else:
            raise ValueError(f"Unsupported field entry {entry}")


def gen_c_struct(name: str, spec) -> str:
    lines = [f"typedef struct __attribute__((packed)) {{"]
    for fname, base, shape in _to_fields(spec):
        ctype = _C_TYPES[np.dtype(base).type]
        dims = "".join(f"[{d}]" for d in shape)
        lines.append(f"    {ctype} {fname}{dims};")
    lines.append(f"}} {name}_t;")
    return "\n".join(lines)


def gen_all_structs(registry: dict[str, object]) -> str:
    r = lambda v: v() if callable(v) else v
    return "\n\n".join(gen_c_struct(k, r(v)) for k, v in registry.items())


# ---- example usage -------------------------------------------------
if __name__ == "__main__":
    path = "types.h"
    types = all_types()
    structs = gen_all_structs(types)
    guard = path.upper().replace(".", "_")

    header = f"""\
#ifndef {guard}
#define {guard}

#include <stdint.h>
#include <stdbool.h>

{structs}

#endif /* {guard} */
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(header)
