#!/usr/bin/env bash
# Быстрая проверка фронтенда без Docker: синтаксис ES-модулей и запрещённые конструкции
# (те же правила, что в backend/tests/test_frontend_static.py).
set -uo pipefail
cd "$(dirname "$0")/../frontend" || exit 1
fail=0
while IFS= read -r f; do
  node --input-type=module --check < "$f" 2>/tmp/check_frontend.err || { echo "SYNTAX: $f"; cat /tmp/check_frontend.err; fail=1; }
done < <(find . -name '*.js')
banned='localStorage|sessionStorage|indexedDB|document\.cookie|Math\.random|innerHTML\s*=|outerHTML|insertAdjacentHTML|document\.write|eval\(|new Function|setAttribute\(["'"'"']style'
if grep -rnE "$banned" --include='*.js' --include='*.html' . ; then echo "BANNED construct found"; fail=1; fi
if grep -rnE '<style|\sstyle=|\son[a-z]+=|<script>|(src|href)=["'"'"']https?://' --include='*.html' . ; then echo "BANNED html found"; fail=1; fi
(( fail == 0 )) && echo "frontend check: OK"
exit $fail
