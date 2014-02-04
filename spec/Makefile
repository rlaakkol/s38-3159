
slides.pdf: \
	headerfmt.txt messages.tex \
	figures/subscribe_normal.png figures/subscribe_lost.png figures/publish_normal.png

%.pdf: %.tex
	pdflatex $*

figures/%.svg: figures/%.msc
	mscgen -T svg -o $@ $<

figures/%.png: figures/%.msc
	mscgen -T svg -o $@ $<
