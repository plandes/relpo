##@meta {desc: 'build and deployment for python projects', date: '2025-04-17'}


## Build
#
PROJ_TYPE=		python
PROJ_MODULES =		python/doc python/deploy

# ignore relpo invocations used in 'pixi.mk'
PY_RP_RELPO_BIN ?=	true


## Project
#
PY_RP_PROJ_FILES =	test-resources/relpo.yml,test-resources/doc.yml
PY_PYPROJECT_FILE =	$(MTARG)/pyproject.toml

PY_DOMAIN_NAME :=	zensols
PY_PROJECT_NAME :=	relpo
PY_GITHUB_USER :=	$(shell git remote -v | grep github | head -1 | \
				sed -E 's/.*:([^/]+).*/\1/')
PY_VERSION :=		$(shell grep -E '^version' pyproject.toml | \
				sed 's/.*\"\(.*\)\"$$/\1/')
# invoke arguments
PY_HELP_ARGS ?=		invoke '--help'
PY_RUN_ARGS ?=		--config $(PY_RP_PROJ_FILES_) --tmp $(MTARG)


## Includes
#
include ./zenbuild/main.mk


## Targets
#
# synthetized relpo.yml
.PHONY:			rpbuildconfig
rpbuildconfig:
			@$(PY_PX_BIN) run invoke 'config $(PY_RUN_ARGS)'

# create the project metadata JSON file
.PHONY:			rpmetafilejson
rpmetafilejson:
			@$(PY_PX_BIN) run invoke \
				'meta $(PY_RUN_ARGS) -v'

# create the project metadata YAML file
.PHONY:			rpmetafileyaml
rpmetafileyaml:
			@$(PY_PX_BIN) run invoke \
				'meta $(PY_RUN_ARGS) -v -f yaml'

# make a tag using the version of the last commit
.PHONY:			rpmktag
rpmktag:
			@$(PY_PX_BIN) run invoke 'mktag $(PY_RUN_ARGS)'

# delete the last tag and create a new one on the latest commit
.PHONY:			rpbumptag
rpbumptag:
			@$(PY_PX_BIN) run invoke 'bumptag $(PY_RUN_ARGS)'

# print this repo's info
.PHONY:			rpcheck
rpcheck:
			@$(PY_PX_BIN) run invoke 'check $(PY_RUN_ARGS)'

# deploy local documentation
.PHONY:			rpdocdeploy
rpdocdeploy:
			make PY_RP_RELPO_BIN=relpo pydocdeploy

.PHONY:			rpgitdocdeploy
rpgitdocdeploy:
			make PY_RP_RELPO_BIN=relpo pygitdocdeploy

.PHONY:			rpdochtml
rpdochtml:
			@RP_DOC_IM_URL="https://plandes.github.io" \
				$(PY_PX_BIN) run invoke \
				'mkdoc $(PY_RUN_ARGS) -o $(MTARG)/doc/build'


## Test
#
# project metadata yaml file test
.PHONY:			testmetafileyaml
testmetafileyaml:
			$(eval cor=91)
			$(eval testfile=$(MTARG)/metafile.yaml)
			@rm -fr $(MTARG)
			@mkdir -p $(dir $(testfile))
			@make rpmetafileyaml --no-print-directory 2>/dev/null | \
				tail -n +2 > $(testfile)
			@cat $(testfile) | wc -l | xargs -i{} bash -c \
			  "if [ '{}' != '$(cor)' ] ; then \
				echo line count differs: {} != $(cor) ; \
				cat $(testfile) ; \
				exit 1 ; \
			  fi"
			@echo "test YAML metadata...ok"

# project metadata json file test
.PHONY:			testmetafilejson
testmetafilejson:
			@make rpmetafilejson --no-print-directory 2>/dev/null | \
				tail -n +2 | \
				jq 'del(.date, .path, .change_log, .repo)' | \
				diff - test-resources/meta-gold.json
			@echo "test JSON metadata...ok"

# integration tests
.PHONY:			testint
testint:		testmetafileyaml testmetafilejson

.PHONY:			testall
testall:		testint
