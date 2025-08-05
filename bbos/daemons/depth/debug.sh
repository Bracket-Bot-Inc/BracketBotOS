for f in cache/frame*_{right,left}.jpg; do
  points=$(< cache/corners.vnl vnl-filter --perl "filename eq \"$f\"" -p x,y,size='2**(1-level)')
  if [[ -n $points ]]; then
    echo "$points" | feedgnuplot \
      --unset key \
      --image "$f" \
      --domain \
      --square \
      --tuplesizeall 3 \
      --with 'points pt 7 ps variable' \
      --hardcopy "${f%.jpg}_corners.png"
  else
    echo "Skipped $f: no matching points in corners.vnl"
  fi
done
