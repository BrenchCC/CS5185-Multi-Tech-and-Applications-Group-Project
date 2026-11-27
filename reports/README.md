# Course reports

- [Project report](project_report/project_report.pdf): system design, methods, results, limitations, member contributions and sources. Its editable source uses the supplied IEEEtran class.
- [Experimental results](exp_report/experiment_report.pdf): all 72 local results, held-out video examples, feature curves, feedback records and the three Ark cases.

Build from the repository root with a LaTeX installation containing the standard packages:

```bash
pdflatex -interaction=nonstopmode -halt-on-error -output-directory=reports/project_report reports/project_report/project_report.tex
pdflatex -interaction=nonstopmode -halt-on-error -output-directory=reports/exp_report reports/exp_report/experiment_report.tex
```

Run each command twice for references and table layout. The experimental source reads figures from `experiments/full_exps/figures/`. See [full experiment records](../experiments/full_exps/README.md) for CSV data, logs and the location of playable outputs. The reports do not bundle the course videos or their licenses. Include the required dataset permissions and video files in the final submission as appropriate.

## Chinese reports

- [项目报告（中文）](project_report/project_report_zh.pdf)，[LaTeX 源码](project_report/project_report_zh.tex)。
- [实验结果（中文）](exp_report/experiment_report_zh.pdf)，[LaTeX 源码](exp_report/experiment_report_zh.tex)。

The Chinese reports use XeLaTeX, ctex and the macOS Songti SC and Heiti SC fonts. Build from the repository root and run each command twice:

```bash
xelatex -interaction=nonstopmode -halt-on-error -output-directory=reports/project_report reports/project_report/project_report_zh.tex
xelatex -interaction=nonstopmode -halt-on-error -output-directory=reports/exp_report reports/exp_report/experiment_report_zh.tex
```

The workflow diagram is supplied as [Mermaid source](figures/encoding_workflow.mmd); the reports include a matching vector diagram generated with Graphviz. The expanded appendices use the existing full-experiment figures and task measurements.

The Chinese project report uses a two-column layout and follows the English project report's section order, evidence tables, examples and appendices.
