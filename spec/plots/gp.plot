set terminal pdf font "cmr10"
set output outfile
set ytics border nomirror
set grid back
set xrange [0:50]
set yrange [0:10]
set xlabel "Packet loss rate (%)"
set ylabel "Time since last update (s)"
#set style fill transparent solid 0.5 noborder
plot datafile using 1:4 w points pt 7 lc rgb "blue" title "Average", datafile using 1:2 w points pt 9 lc rgb "red" title "Maximum"

