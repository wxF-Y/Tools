import re
import os
import sys
import codecs

def process_file(filepath):
    # 尝试多种编码打开文件
    encodings = ['utf-8-sig', 'utf-8', 'gbk', 'gb2312', 'gb18030', 'latin-1']
    content = None
    used_encoding = None
    
    for encoding in encodings:
        try:
            with codecs.open(filepath, 'r', encoding=encoding) as f:
                content = f.read()
                used_encoding = encoding
                break
        except (UnicodeDecodeError, UnicodeError):
            continue
        except Exception as e:
            print(f"Error reading {filepath} with {encoding}: {e}")
            continue
    
    if content is None:
        print(f"Failed to read {filepath} with any encoding. Skipping...")
        return
    
    print(f"Successfully read {filepath} using {used_encoding} encoding")
    
    placeholders = []
    
    def save_placeholder(text):
        idx = len(placeholders)
        placeholders.append(text)
        return f"<<<PLACEHOLDER_{idx}>>>"
    
    # 1. 保护注释
    def protect_comments(content):
        result = []
        i = 0
        while i < len(content):
            if content[i:i+2] == '/*':
                comment_start = i
                i += 2
                while i < len(content) - 1:
                    if content[i:i+2] == '*/':
                        i += 2
                        result.append(save_placeholder(content[comment_start:i]))
                        break
                    i += 1
                else:
                    result.append(content[comment_start:])
                    break
            elif content[i:i+2] == '//':
                comment_start = i
                i += 2
                while i < len(content) and content[i] not in '\r\n':
                    i += 1
                result.append(save_placeholder(content[comment_start:i]))
            else:
                result.append(content[i])
                i += 1
        return ''.join(result)
    
    content = protect_comments(content)
    
    # 2. 保护预处理指令
    def protect_preprocessor(content):
        lines = content.split('\n')
        result = []
        for line in lines:
            stripped = line.lstrip()
            if stripped.startswith('#include') or stripped.startswith('#pragma'):
                result.append(save_placeholder(line))
            else:
                result.append(line)
        return '\n'.join(result)
    
    content = protect_preprocessor(content)
    
    # 3. 保护 extern "C"
    def protect_extern_c(content):
        result = []
        i = 0
        while i < len(content):
            if content[i:].startswith('<<<PLACEHOLDER_'):
                end = content.find('>>>', i + 15)
                if end != -1:
                    result.append(content[i:end + 3]);
                    i = end + 3;
                    continue;
            
            if content[i:].startswith('extern'):
                j = i + 6
                while j < len(content) and content[j] in ' \t\r\n':
                    j += 1
                
                if j + 2 < len(content) and content[j:j+3] == '"C"':
                    result.append(content[i:j])
                    result.append(save_placeholder('"C"'))
                    j += 3
                    i = j
                    
                    while j < len(content) and content[j] in ' \t\r\n':
                        j += 1
                    
                    if j < len(content) and content[j] == '{':
                        brace_count = 1
                        j += 1
                        block_start = j
                        
                        while j < len(content) and brace_count > 0:
                            if content[j] == '{':
                                brace_count += 1
                            elif content[j] == '}':
                                brace_count -= 1
                                if brace_count == 0:
                                    break
                            j += 1
                        
                        if brace_count == 0:
                            result.append(' {')
                            result.append(save_placeholder(content[block_start:j]))
                            result.append('}')
                            i = j + 1
                            continue
                    continue
            
            result.append(content[i])
            i += 1
        return ''.join(result)
    
    content = protect_extern_c(content)
    
    # 4. 保护已包裹的宏
    def protect_wrapped_macros(content):
        result = []
        i = 0
        macros = ['DYN_MAKE_STR_Ws', 'DYN_MAKE_STR_W', 'CONSTEXPR_WSTR',
                  'DYN_MAKE_STR_As', 'DYN_MAKE_STR_A', 'CONSTEXPR_STR']
        
        while i < len(content):
            if content[i:].startswith('<<<PLACEHOLDER_'):
                end = content.find('>>>', i + 15)
                if end != -1:
                    result.append(content[i:end + 3])
                    i = end + 3
                    continue
            
            matched = None
            for macro in macros:
                if content[i:].startswith(macro):
                    j = i + len(macro)
                    while j < len(content) and content[j] in ' \t':
                        j += 1
                    if j < len(content) and content[j] == '(':
                        matched = macro
                        break
            
            if matched:
                start = i
                i += len(matched)
                while i < len(content) and content[i] in ' \t':
                    i += 1
                
                if i < len(content) and content[i] == '(':
                    i += 1
                    count = 1
                    
                    while i < len(content) and count > 0:
                        # 简单的括号计数，假设宏内的字符串已经正确格式化
                        if content[i] == '(':
                            count += 1
                        elif content[i] == ')':
                            count -= 1
                        i += 1
                    
                    result.append(save_placeholder(content[start:i]))
                else:
                    result.append(content[start:i])
            else:
                result.append(content[i])
                i += 1
        
        return ''.join(result)
    
    content = protect_wrapped_macros(content)
    
    # 5. 保护原始字符串 R"()" 和 LR"()" - 不对它们进行处理
    def protect_raw_strings(content):
        result = []
        i = 0
        
        while i < len(content):
            if content[i:].startswith('<<<PLACEHOLDER_'):
                end = content.find('>>>', i + 15)
                if end != -1:
                    result.append(content[i:end + 3])
                    i = end + 3
                    continue
            
            # 检查是否是原始字符串的开始
            start = i
            
            if content[i:i+3] == 'LR"':
                prefix_len = 3
            elif content[i:i+2] == 'R"':
                prefix_len = 2
            else:
                result.append(content[i])
                i += 1
                continue
            
            # 找到原始字符串并保护它
            i += prefix_len
            
            # 读取分隔符
            delim_start = i
            while i < len(content) and content[i] != '(':
                i += 1
            
            if i >= len(content):
                result.append(content[start:])
                break
            
            delimiter = content[delim_start:i]
            i += 1  # 跳过 '('
            
            # 查找结束标记
            end_marker = ')' + delimiter + '"'
            
            while i < len(content):
                if content[i:i+len(end_marker)] == end_marker:
                    i += len(end_marker)
                    # 保护整个原始字符串
                    raw_str = content[start:i]
                    result.append(save_placeholder(raw_str))
                    break
                i += 1
            else:
                # 没找到结束标记
                result.append(content[start:])
                break
        
        return ''.join(result)
    
    content = protect_raw_strings(content)
    
    # 6. 处理 _T 宏 - 转换后立即保护
    def process_t_macro(content):
        result = []
        i = 0
        
        while i < len(content):
            if content[i:].startswith('<<<PLACEHOLDER_'):
                end = content.find('>>>', i + 15)
                if end != -1:
                    result.append(content[i:end + 3])
                    i = end + 3
                    continue
            
            if content[i:i+2] == '_T':
                j = i + 2
                while j < len(content) and content[j] in ' \t':
                    j += 1
                
                if j < len(content) and content[j] == '(':
                    j += 1
                    while j < len(content) and content[j] in ' \t':
                        j += 1
                    
                    if j < len(content) and content[j] == '"':
                        str_start = j
                        j += 1
                        escaped = False
                        
                        while j < len(content):
                            if escaped:
                                escaped = False
                                j += 1
                                continue
                            if content[j] == '\\':
                                escaped = True
                                j += 1
                                continue
                            if content[j] == '"':
                                j += 1
                                break
                            j += 1
                        
                        while j < len(content) and content[j] in ' \t':
                            j += 1
                        
                        if j < len(content) and content[j] == ')':
                            j += 1
                            str_content = content[str_start:j-1].strip()
                            # 转换并立即保护，避免后续被重复处理
                            converted = f'CONSTEXPR_WSTR(L{str_content})'
                            result.append(save_placeholder(converted))
                            i = j
                            continue
            
            result.append(content[i])
            i += 1
        
        return ''.join(result)
    
    content = process_t_macro(content)
    
    # 7. 包裹普通字符串
    def wrap_normal_strings(content):
        result = []
        i = 0
        
        while i < len(content):
            if content[i:].startswith('<<<PLACEHOLDER_'):
                end = content.find('>>>', i + 15)
                if end != -1:
                    result.append(content[i:end + 3])
                    i = end + 3
                    continue
            
            # 宽字符串
            if content[i:i+2] == 'L"':
                j = i + 2
                escaped = False
                
                while j < len(content):
                    if escaped:
                        escaped = False
                        j += 1
                        continue
                    if content[j] == '\\':
                        escaped = True
                        j += 1
                        continue
                    if content[j] == '"':
                        k = j + 1
                        while k < len(content) and content[k] in ' \t\r\n':
                            k += 1
                        
                        if k + 1 < len(content) and content[k:k+2] == 'L"':
                            j = k + 2
                            continue
                        else:
                            result.append(f'CONSTEXPR_WSTR({content[i:j+1]})')
                            i = j + 1
                            break
                    j += 1
                else:
                    result.append(content[i])
                    i += 1
            # 窄字符串
            elif content[i] == '"' and (i == 0 or content[i-1] != 'L'):
                j = i + 1
                escaped = False
                
                while j < len(content):
                    if escaped:
                        escaped = False
                        j += 1
                        continue
                    if content[j] == '\\':
                        escaped = True
                        j += 1
                        continue
                    if content[j] == '"':
                        k = j + 1
                        while k < len(content) and content[k] in ' \t\r\n':
                            k += 1
                        
                        if k < len(content) and content[k] == '"':
                            j = k + 1
                            continue
                        else:
                            result.append(f'CONSTEXPR_STR({content[i:j+1]})')
                            i = j + 1
                            break
                    j += 1
                else:
                    result.append(content[i])
                    i += 1
            else:
                result.append(content[i])
                i += 1
        
        return ''.join(result)
    
    content = wrap_normal_strings(content)
    
    # 还原占位符
    for i in range(len(placeholders) - 1, -1, -1):
        content = content.replace(f'<<<PLACEHOLDER_{i}>>>', placeholders[i])
    
    # 写入文件，统一使用 UTF-8 with BOM 编码
    try:
        with codecs.open(filepath, 'w', encoding='utf-8-sig') as f:
            f.write(content)
        print(f"Successfully wrote {filepath} using utf-8-sig encoding")
    except Exception as e:
        print(f"Error writing {filepath}: {e}")

def process_dir(rootdir):
    for dirpath, _, filenames in os.walk(rootdir):
        for filename in filenames:
            if filename.endswith('.cpp') or filename.endswith('.h'):
                filepath = os.path.join(dirpath, filename)
                print(f"Processing: {filepath}")
                process_file(filepath)

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("用法: python conv_new.py <目录或文件路径>")
        sys.exit(1)
    
    path = sys.argv[1]
    if os.path.isfile(path):
        if path.endswith('.cpp') or path.endswith('.h'):
            print(f"Processing: {path}")
            process_file(path)
        else:
            print(f"跳过非C++文件: {path}")
    elif os.path.isdir(path):
        process_dir(path)
    else:
        print(f"路径不存在: {path}")
        sys.exit(1)
