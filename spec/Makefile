all: documentation.pdf doc.pdf slides.pdf

documentation.pdf: \
	documentation-cover.tex \
	AssignmentDiary.tex commit_log.txt plots/plotdata.pdf

doc.pdf: \
	doc-cover.tex headerfmt.txt messages.tex \
	figures/subscribe_normal.pdf figures/subscribe_lost.pdf figures/publish_normal.pdf

slides.pdf: \
	headerfmt.txt messages.tex \
	figures/subscribe_normal.pdf figures/subscribe_lost.pdf figures/publish_normal.pdf figures/teardown.pdf

%.pdf: %.tex
	latexmk -pdf $*

%.tex: %.txt
	pandoc -t latex -o $@ -f markdown $<

AssignmentDiary.tex: AssignmentDiary.txt
	pandoc -t latex -f markdown $< | sed 's/section/section*/' > $@

%.pdf: %.txt
	pandoc -o $@ -f markdown $<

figures/%.svg: figures/%.msc
	mscgen -T svg -o $@ $<

figures/%.pdf: figures/%.svg
	inkscape  --export-pdf=$@ $<

figures/%.png: figures/%.msc
	mscgen -T svg -o $@ $<

plots/%.pdf: plots/%.dat plots/gp.plot
	gnuplot -e "outfile='$@'; datafile='$<'" plots/gp.plot

commit_log.txt:
	git log --date=short --pretty=format:"%w(80)%cd: %B" > $@
