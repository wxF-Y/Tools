#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
通用字符串字面量包裹工具 - 将 C++ 源代码中未包裹的字符串字面量
用指定的宏（默认 CONSTEXPR_WSTR / CONSTEXPR_STR）包裹起来，
用于字符串混淆/反病毒规避等场景。

跳过条件:
1. 预处理器行 (#define, #include, #pragma 等)
2. 已经被包裹的字符串 (DYN_MAKE_STR_*, CONSTEXPR_WSTR, _T 等)
3. 数组初始化: WCHAR/wchar_t/char name[...] = "..."
4. 非const指针赋值: wchar_t*/LPWSTR 等 name = L"..."
5. extern "C" / extern "C++" 链接说明符
6. 字符字面量 L'\0' 等

支持文件编码：UTF-8（含/不含 BOM）

用法：
  python wrap_constexpr_str.py [选项] [PATH]

示例：
  # 处理当前目录
  python wrap_constexpr_str.py

  # 处理指定目录，dry-run 预览
  python wrap_constexpr_str.py --dry-run E:/myproject

  # 自定义跳过目录和文件
  python wrap_constexpr_str.py --skip-dir 3rdparty --skip-dir vendor

  # 自定义包裹宏
  python wrap_constexpr_str.py --wide-macro MY_WSTR --narrow-macro MY_STR

  # 只处理特定扩展名
  python wrap_constexpr_str.py --ext cpp --ext h
"""

import argparse
import os
import re
import glob
import sys


# ---------- 默认配置 ----------

DEFAULT_SKIP_DIRS = ['.git', '.svn', '.hg', 'node_modules', '.claude']

DEFAULT_SKIP_FILES = ['resource.h']

DEFAULT_SKIP_BASENAME_PREFIXES = ['version']  # version*.h 之类

DEFAULT_SKIP_EXTENSIONS = ['.rc']

DEFAULT_EXTENSIONS = ['cpp', 'h', 'c', 'hpp', 'cc', 'cxx']

# 这些宏的参数已被包裹/视为编译期常量，不再处理
DEFAULT_WRAPPER_MACROS = [
    # 项目自定义包裹宏
    'DYN_MAKE_STR_W', 'DYN_MAKE_STR_A', 'DYN_MAKE_STR_Ws', 'DYN_MAKE_STR_As',
    'DYN_MAKE_STR_T', 'DYN_MAKE_STR_Ts',
    'CONSTEXPR_WSTR', 'CONSTEXPR_STR', 'CONSTEXPR_TSTR',
    'AY_OBF', 'AY_OBFUSCATE',
    # TCHAR 包裹宏
    '_T', '_TEXT', 'TEXT',
    # 编译期需要字符串字面量的内置
    'MAKEINTRESOURCE', 'MAKEINTRESOURCEA', 'MAKEINTRESOURCEW',
    'sizeof', '_countof', 'ARRAYSIZE', '_ARRAYSIZE',
    'static_assert', '__declspec',
]


# ---------- 正则模式 ----------

# 非const指针赋值: wchar_t* p = "...", LPWSTR p = L"..."
# 使用 \s*$ 确保字符串字面量是赋值右侧的直接值（而非函数参数）
NONCONST_PTR_RE = re.compile(
    r'\b(?:(?:wchar_t|WCHAR|char|CHAR)\s*\*+\s*|'
    r'(?:LPWSTR|PWSTR|LPSTR|PSTR)\s+)\w+\s*=\s*$'
)

# 数组初始化: WCHAR name[] = L"...", char name[N] = "..."
ARRAY_INIT_RE = re.compile(
    r'\b(?:wchar_t|WCHAR|TCHAR|char|CHAR)\s+\w+\s*\[[\w\s*+\-]*\]\s*=\s*$'
)

# extern "C" / extern "C++"
EXTERN_LINKAGE_RE = re.compile(r'\bextern\s*$')


# ---------- 核心解析 ----------

def find_skip_zones(content, wrapper_macros):
    """
    返回 [(start, end), ...] 的跳过区间列表。
    包含: 行注释、块注释、预处理器行、已包裹宏的整个调用范围。
    """
    skip_zones = []
    i = 0
    n = len(content)

    while i < n:
        # 行注释 //...
        if content[i:i+2] == '//':
            j = i + 2
            while j < n and content[j] != '\n':
                j += 1
            skip_zones.append((i, j))
            i = j
            continue

        # 块注释 /* ... */
        if content[i:i+2] == '/*':
            j = content.find('*/', i + 2)
            j = n if j == -1 else j + 2
            skip_zones.append((i, j))
            i = j
            continue

        # 跳过字符串和字符字面量（避免将其内部误判为注释/预处理）
        if content[i] == 'L' and i + 1 < n and content[i+1] in ('"', "'"):
            quote = content[i+1]
            j = i + 2
            while j < n:
                if content[j] == '\\':
                    j += 2
                elif content[j] == quote:
                    j += 1
                    break
                else:
                    j += 1
            i = j
            continue

        if content[i] in ('"', "'"):
            quote = content[i]
            j = i + 1
            while j < n:
                if content[j] == '\\':
                    j += 2
                elif content[j] == quote:
                    j += 1
                    break
                else:
                    j += 1
            i = j
            continue

        # 预处理器行（行首只有空白）
        if content[i] == '#':
            line_start = content.rfind('\n', 0, i)
            before = content[:i] if line_start == -1 else content[line_start+1:i]
            if before.strip() == '':
                j = i + 1
                while j < n:
                    if content[j] == '\\' and j + 1 < n and content[j+1] == '\n':
                        j += 2
                    elif content[j] == '\n':
                        break
                    else:
                        j += 1
                skip_zones.append((i, j))
                i = j
                continue

        # 检测包裹宏 WRAPPER_MACRO(...)
        if content[i].isalpha() or content[i] == '_':
            j = i
            while j < n and (content[j].isalnum() or content[j] == '_'):
                j += 1
            word = content[i:j]

            if word in wrapper_macros:
                # 找到开括号
                k = j
                while k < n and content[k] in ' \t':
                    k += 1
                if k < n and content[k] == '(':
                    # 找到匹配的闭括号，同时正确跳过内部字符串
                    depth = 1
                    m = k + 1
                    in_str = False
                    str_char = ''
                    while m < n and depth > 0:
                        c = content[m]
                        if in_str:
                            if c == '\\':
                                m += 2
                                continue
                            if c == str_char:
                                in_str = False
                        else:
                            if c == 'L' and m + 1 < n and content[m+1] in ('"', "'"):
                                in_str = True
                                str_char = content[m+1]
                                m += 1
                            elif c in ('"', "'"):
                                in_str = True
                                str_char = c
                            elif c == '(':
                                depth += 1
                            elif c == ')':
                                depth -= 1
                        m += 1
                    skip_zones.append((i, m))
                    i = m
                    continue

            i = j
            continue

        i += 1

    return skip_zones


def is_in_skip_zone(pos, skip_zones):
    """检查位置是否在任一跳过区间内"""
    for start, end in skip_zones:
        if start <= pos < end:
            return True
    return False


def get_line_before_pos(content, pos):
    """获取当前行中给定位置之前的内容"""
    line_start = content.rfind('\n', 0, pos)
    return content[:pos] if line_start == -1 else content[line_start+1:pos]


def _scan_string_body(content, j, n, quote='"'):
    """从位置 j 开始扫描到字符串结束（即遇到匹配的 quote），返回结束后的位置"""
    while j < n:
        if content[j] == '\\':
            j += 2
        elif content[j] == quote:
            j += 1
            break
        else:
            j += 1
    return j


def find_all_string_literals(content):
    """
    找到所有字符串字面量（含相邻字面量合并）。
    返回: [(start, end, is_wide), ...]

    会跳过注释和预处理器行（防止其中的引号/反斜杠干扰解析）。
    """
    literals = []
    i = 0
    n = len(content)

    while i < n:
        # 跳过行注释
        if content[i:i+2] == '//':
            j = i + 2
            while j < n and content[j] != '\n':
                j += 1
            i = j
            continue

        # 跳过块注释
        if content[i:i+2] == '/*':
            j = content.find('*/', i + 2)
            i = n if j == -1 else j + 2
            continue

        # 跳过预处理器行
        if content[i] == '#':
            line_start = content.rfind('\n', 0, i)
            before = content[:i] if line_start == -1 else content[line_start+1:i]
            if before.strip() == '':
                j = i + 1
                while j < n:
                    if content[j] == '\\' and j + 1 < n and content[j+1] == '\n':
                        j += 2
                    elif content[j] == '\n':
                        break
                    else:
                        j += 1
                i = j
                continue

        # 宽字符串字面量 L"..."
        if content[i] == 'L' and i + 1 < n and content[i+1] == '"':
            start = i
            is_wide = True
            j = _scan_string_body(content, i + 2, n, '"')
            # 相邻字面量合并
            while True:
                k = j
                while k < n and content[k] in ' \t\n\r':
                    k += 1
                if content[k:k+2] == 'L"':
                    j = _scan_string_body(content, k + 2, n, '"')
                elif k < n and content[k] == '"':
                    j = _scan_string_body(content, k + 1, n, '"')
                else:
                    break
            literals.append((start, j, is_wide))
            i = j
            continue

        # 宽字符字面量 L'...' （跳过）
        if content[i] == 'L' and i + 1 < n and content[i+1] == "'":
            j = _scan_string_body(content, i + 2, n, "'")
            i = j
            continue

        # 窄字符串字面量 "..."
        if content[i] == '"':
            start = i
            is_wide = False
            j = _scan_string_body(content, i + 1, n, '"')
            while True:
                k = j
                while k < n and content[k] in ' \t\n\r':
                    k += 1
                if k < n and content[k] == '"':
                    j = _scan_string_body(content, k + 1, n, '"')
                elif content[k:k+2] == 'L"':
                    is_wide = True  # 相邻有宽字符，整体升级为宽
                    j = _scan_string_body(content, k + 2, n, '"')
                else:
                    break
            literals.append((start, j, is_wide))
            i = j
            continue

        # 窄字符字面量 '...' （跳过）
        if content[i] == "'":
            j = _scan_string_body(content, i + 1, n, "'")
            i = j
            continue

        i += 1

    return literals


def should_wrap(content, start, end, is_wide, skip_zones):
    """判断字符串字面量是否应该被包裹"""
    if is_in_skip_zone(start, skip_zones):
        return False

    before = get_line_before_pos(content, start)
    before_stripped = before.strip()

    if ARRAY_INIT_RE.search(before):
        return False
    if NONCONST_PTR_RE.search(before):
        return False
    if EXTERN_LINKAGE_RE.search(before_stripped):
        return False

    return True


# ---------- 文件处理 ----------

def process_file(filepath, wrapper_macros, wide_macro, narrow_macro, dry_run=False):
    """
    处理单个文件，返回 (changed: bool, count: int).
    保留原文件编码（含 BOM）和行尾风格（二进制读写）。
    """
    with open(filepath, 'rb') as f:
        data = f.read()

    has_bom = data.startswith(b'\xef\xbb\xbf')
    raw = data[3:] if has_bom else data
    try:
        content = raw.decode('utf-8')
    except UnicodeDecodeError:
        # 回退到容错解码（极少触发）
        content = raw.decode('utf-8', errors='replace')

    skip_zones = find_skip_zones(content, wrapper_macros)
    literals = find_all_string_literals(content)

    changes = []
    for start, end, is_wide in literals:
        if should_wrap(content, start, end, is_wide, skip_zones):
            literal_text = content[start:end]
            macro = wide_macro if is_wide else narrow_macro
            wrapped = '%s(%s)' % (macro, literal_text)
            changes.append((start, end, wrapped))

    if not changes:
        return False, 0

    if dry_run:
        return True, len(changes)

    # 从后往前应用修改，避免位置漂移
    changes.sort(key=lambda x: -x[0])
    result = list(content)
    for s, e, replacement in changes:
        result[s:e] = list(replacement)
    new_content = ''.join(result)

    with open(filepath, 'wb') as f:
        if has_bom:
            f.write(b'\xef\xbb\xbf')
        f.write(new_content.encode('utf-8'))

    return True, len(changes)


def should_skip_file(filepath, skip_dirs, skip_files, skip_basename_prefixes, skip_extensions):
    """判断文件是否应跳过"""
    fp = filepath.replace('\\', '/')
    basename = os.path.basename(fp)
    basename_lower = basename.lower()

    # 按扩展名跳过
    for ext in skip_extensions:
        if basename_lower.endswith(ext.lower()):
            return True

    # 按完整文件名跳过
    if basename in skip_files or basename_lower in [f.lower() for f in skip_files]:
        return True

    # 按文件名前缀跳过（如 version*.h）
    name_no_ext, ext = os.path.splitext(basename_lower)
    for prefix in skip_basename_prefixes:
        if name_no_ext.startswith(prefix.lower()):
            return True

    # 按目录跳过（子串匹配）
    for skip_dir in skip_dirs:
        if skip_dir in fp:
            return True

    return False


# ---------- 命令行入口 ----------

def parse_args():
    p = argparse.ArgumentParser(
        description='将 C++ 源代码中未包裹的字符串字面量用指定的宏包裹起来',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        'path', nargs='?', default='.',
        help='要处理的根目录（默认: 当前目录）'
    )
    p.add_argument(
        '--wide-macro', default='CONSTEXPR_WSTR',
        help='宽字符串字面量的包裹宏名（默认: CONSTEXPR_WSTR）'
    )
    p.add_argument(
        '--narrow-macro', default='CONSTEXPR_STR',
        help='窄字符串字面量的包裹宏名（默认: CONSTEXPR_STR）'
    )
    p.add_argument(
        '--ext', action='append', default=None,
        help='要处理的文件扩展名（不带点），可多次指定。'
             '默认: cpp/h/c/hpp/cc/cxx'
    )
    p.add_argument(
        '--skip-dir', action='append', default=[],
        help='要跳过的目录（子串匹配），可多次指定'
    )
    p.add_argument(
        '--skip-file', action='append', default=[],
        help='要跳过的文件名（完整匹配），可多次指定'
    )
    p.add_argument(
        '--skip-prefix', action='append', default=[],
        help='要跳过的文件名前缀（如 version），可多次指定'
    )
    p.add_argument(
        '--skip-ext', action='append', default=[],
        help='要跳过的扩展名（如 .rc），可多次指定'
    )
    p.add_argument(
        '--wrapper-macro', action='append', default=[],
        help='额外的"已包裹"宏名（其参数会被视为已处理），可多次指定'
    )
    p.add_argument(
        '--dry-run', action='store_true',
        help='预览模式：只报告将要做的修改，不实际写文件'
    )
    p.add_argument(
        '--verbose', '-v', action='store_true',
        help='详细输出'
    )
    p.add_argument(
        '--max-iters', type=int, default=10,
        help='重复运行直到收敛的最大轮次（默认: 10）'
    )
    return p.parse_args()


def collect_files(root, extensions, skip_dirs, skip_files, skip_basename_prefixes, skip_extensions):
    """收集要处理的所有文件"""
    files = []
    for ext in extensions:
        pattern = os.path.join(root, '**', '*.' + ext.lstrip('.'))
        for f in glob.glob(pattern, recursive=True):
            if not should_skip_file(f, skip_dirs, skip_files, skip_basename_prefixes, skip_extensions):
                files.append(f)
    return sorted(set(files))


def run_one_pass(files, wrapper_macros, wide_macro, narrow_macro, root, dry_run, verbose):
    """运行一轮处理，返回 (修改文件数, 替换总数)"""
    modified = 0
    total_changes = 0

    for filepath in files:
        try:
            changed, count = process_file(filepath, wrapper_macros, wide_macro, narrow_macro, dry_run)
            if changed:
                rel = os.path.relpath(filepath, root)
                action = '[DRY-RUN]' if dry_run else 'Fixed'
                print('  %s (%3d): %s' % (action, count, rel))
                modified += 1
                total_changes += count
        except Exception as e:
            rel = os.path.relpath(filepath, root)
            print('  ERROR in %s: %s' % (rel, e), file=sys.stderr)

    return modified, total_changes


def main():
    args = parse_args()

    root = os.path.abspath(args.path)
    if not os.path.isdir(root):
        print('错误: 路径不存在或不是目录: %s' % root, file=sys.stderr)
        return 1

    # 整合配置
    extensions = args.ext if args.ext else DEFAULT_EXTENSIONS
    skip_dirs = DEFAULT_SKIP_DIRS + args.skip_dir
    skip_files = DEFAULT_SKIP_FILES + args.skip_file
    skip_basename_prefixes = DEFAULT_SKIP_BASENAME_PREFIXES + args.skip_prefix
    skip_extensions = DEFAULT_SKIP_EXTENSIONS + args.skip_ext
    wrapper_macros = set(DEFAULT_WRAPPER_MACROS) | set(args.wrapper_macro) | {args.wide_macro, args.narrow_macro}

    if args.verbose:
        print('Root: %s' % root)
        print('Extensions: %s' % extensions)
        print('Skip dirs: %s' % skip_dirs)
        print('Skip files: %s' % skip_files)
        print('Skip prefixes: %s' % skip_basename_prefixes)
        print('Skip extensions: %s' % skip_extensions)
        print('Wide macro: %s' % args.wide_macro)
        print('Narrow macro: %s' % args.narrow_macro)
        print('Wrapper macros: %s' % sorted(wrapper_macros))
        print('Dry-run: %s' % args.dry_run)
        print()

    files = collect_files(root, extensions, skip_dirs, skip_files, skip_basename_prefixes, skip_extensions)

    if not files:
        print('未找到匹配的源文件')
        return 0

    print('共找到 %d 个文件' % len(files))
    print()

    # 多轮迭代直到收敛（因相邻字面量等导致单轮可能不完整）
    grand_total_changes = 0
    grand_modified_files = set()

    for round_idx in range(1, args.max_iters + 1):
        print('=== 第 %d 轮 ===' % round_idx)
        modified, changes = run_one_pass(
            files, wrapper_macros, args.wide_macro, args.narrow_macro, root, args.dry_run, args.verbose
        )
        print()
        print('本轮: 修改 %d 文件, 替换 %d 次' % (modified, changes))

        if changes == 0:
            print('已收敛')
            break

        grand_total_changes += changes

        # dry-run 模式下不重复运行（因为不实际写入，下一轮结果相同）
        if args.dry_run:
            break

    print()
    print('=' * 40)
    print('总计替换次数: %d' % grand_total_changes)

    return 0


if __name__ == '__main__':
    sys.exit(main())
