doc.pdf: \
	doc-cover.tex headerfmt.txt messages.tex \
	figures/subscribe_normal.pdf figures/subscribe_lost.pdf figures/publish_normal.pdf

slides.pdf: \
	headerfmt.txt messages.tex \
	figures/subscribe_normal.pdf figures/subscribe_lost.pdf figures/publish_normal.pdf

%.pdf: %.tex
	pdflatex $*

figures/%.svg: figures/%.msc
	mscgen -T svg -o $@ $<

figures/%.pdf: figures/%.svg
	inkscape  --export-pdf=$@ $<

figures/%.png: figures/%.msc
	mscgen -T svg -o $@ $<
