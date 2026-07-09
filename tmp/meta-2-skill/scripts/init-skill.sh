#!/bin/bash
# 输入: 目标目录的绝对路径
# 输出: 在目标路径下创建符合 skill 目录规范的空目录结构
# 确定性: 目录结构格式固定，纯文件系统操作，每次执行结果相同

set -e

TARGET_DIR="$1"

if [ -z "$TARGET_DIR" ]; then
    echo "Usage: init-skill.sh <target-skill-directory>"
    exit 1
fi

mkdir -p "$TARGET_DIR"
mkdir -p "$TARGET_DIR/references"
mkdir -p "$TARGET_DIR/scripts"
mkdir -p "$TARGET_DIR/assets"

echo "Skill directory structure created at: $TARGET_DIR"
