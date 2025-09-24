# Font Path Migration Guide

## 🚨 Problem: Hardcoded Font Paths

Previously, font paths were hardcoded throughout the codebase with ridiculous paths like:

```python
# ❌ OLD WAY - Hardcoded paths with multiple parent directories
MATERIAL_SYMBOLS_FONT_PATH = (Path(__file__).parent.parent.parent.parent / 
                              "microdrop_style" / "icons" / "Material_Symbols_Outlined" / 
                              "MaterialSymbolsOutlined-VariableFont_FILL,GRAD,opsz,wght.ttf")
```

This approach was:
- **Error-prone** - Easy to miscount parent directories
- **Hard to maintain** - Paths break when files are moved
- **Inconsistent** - Different files used different path calculations
- **Not portable** - Paths were tied to specific file locations

## ✅ Solution: Centralized Font Path Management

We've created a new `microdrop_style.font_paths` module that provides clean, centralized access to font files.

### **New API:**

```python
# ✅ NEW WAY - Clean, centralized API
from microdrop_style.font_paths import (
    get_material_symbols_font_path,
    load_material_symbols_font,
    get_font_path
)

# Get the font path
font_path = get_material_symbols_font_path()

# Load the font and get family name
font_family = load_material_symbols_font()

# Generic font access
font_path = get_font_path('material_symbols')
```

## 🔧 Migration Steps

### **1. Replace Hardcoded Paths:**

```python
# Before:
MATERIAL_SYMBOLS_FONT_PATH = (Path(__file__).parent.parent.parent.parent / 
                              "microdrop_style" / "icons" / "Material_Symbols_Outlined" / 
                              "MaterialSymbolsOutlined-VariableFont_FILL,GRAD,opsz,wght.ttf")
ICON_FONT_FAMILY = load_font_family(MATERIAL_SYMBOLS_FONT_PATH) or "Material Symbols Outlined"

# After:
from microdrop_style.font_paths import load_material_symbols_font
ICON_FONT_FAMILY = load_material_symbols_font() or "Material Symbols Outlined"
```

### **2. Available Font Functions:**

| Function | Description | Returns |
|----------|-------------|---------|
| `get_material_symbols_font_path()` | Get Material Symbols Outlined font path | `Path` |
| `get_material_symbols_rounded_font_path()` | Get Material Symbols Rounded font path | `Path` |
| `get_material_symbols_sharp_font_path()` | Get Material Symbols Sharp font path | `Path` |
| `get_inter_font_path()` | Get Inter font path | `Path` |
| `get_inter_italic_font_path()` | Get Inter Italic font path | `Path` |
| `get_font_path('font_name')` | Generic font path getter | `Path` |

### **3. Font Loading Functions:**

| Function | Description | Returns |
|----------|-------------|---------|
| `load_material_symbols_font()` | Load Material Symbols font | `Optional[str]` |
| `load_inter_font()` | Load Inter font | `Optional[str]` |
| `load_font_and_get_family('font_name')` | Generic font loader | `Optional[str]` |

## 🎯 Benefits

### **✅ Maintainability:**
- **Single source of truth** for font paths
- **Easy to update** when font locations change
- **Consistent path resolution** across the codebase

### **✅ Reliability:**
- **No more path counting errors** (`parent.parent.parent.parent`)
- **Automatic path validation** with helpful error messages
- **Fallback handling** when fonts can't be loaded

### **✅ Developer Experience:**
- **Clean, readable code** without path manipulation
- **Type hints** for better IDE support
- **Comprehensive error messages** for debugging

### **✅ Portability:**
- **Works from any location** in the codebase
- **No dependency on file structure** for path calculation
- **Easy to test** and validate

## 🚀 Usage Examples

### **Basic Font Path Access:**
```python
from microdrop_style.font_paths import get_material_symbols_font_path

# Get the font path
font_path = get_material_symbols_font_path()
print(f"Font located at: {font_path}")
```

### **Font Loading with Fallback:**
```python
from microdrop_style.font_paths import load_material_symbols_font

# Load font and get family name
font_family = load_material_symbols_font() or "Material Symbols Outlined"
print(f"Using font: {font_family}")
```

### **Generic Font Access:**
```python
from microdrop_style.font_paths import get_font_path, load_font_and_get_family

# Get any font by name
font_path = get_font_path('material_symbols')
font_family = load_font_and_get_family('inter')
```

### **Error Handling:**
```python
from microdrop_style.font_paths import get_font_path

try:
    font_path = get_font_path('material_symbols')
    # Use font_path...
except FileNotFoundError as e:
    print(f"Font not found: {e}")
except ValueError as e:
    print(f"Invalid font name: {e}")
```

## 🔍 Available Font Names

Use these names with `get_font_path()` and `load_font_and_get_family()`:

- `'material_symbols'` → Material Symbols Outlined
- `'material_symbols_rounded'` → Material Symbols Rounded  
- `'material_symbols_sharp'` → Material Symbols Sharp
- `'inter'` → Inter Variable Font
- `'inter_italic'` → Inter Italic Variable Font

## 🧪 Testing

Run the test script to verify the new system works:

```bash
python examples/test_font_paths.py
```

## 📝 Migration Checklist

- [ ] Replace hardcoded `MATERIAL_SYMBOLS_FONT_PATH` variables
- [ ] Import from `microdrop_style.font_paths`
- [ ] Use appropriate font loading functions
- [ ] Remove unused `Path` imports if no longer needed
- [ ] Test that fonts load correctly
- [ ] Update any documentation referencing old paths

## 🎉 Result

After migration, your code will be:
- **Cleaner** - No more path manipulation
- **More reliable** - Centralized path management
- **Easier to maintain** - Single place to update font paths
- **More professional** - Following Python best practices
