@echo off
echo Compilation du rapport en cours (etape 1/2)...
docker run --rm -v "%cd%:/data" -w /data blang/latex:ubuntu pdflatex -interaction=nonstopmode rapport_data_breach_monitor.tex

echo Compilation du rapport en cours (etape 2/2 pour la table des matieres)...
docker run --rm -v "%cd%:/data" -w /data blang/latex:ubuntu pdflatex -interaction=nonstopmode rapport_data_breach_monitor.tex

echo Compilation terminee !
pause
