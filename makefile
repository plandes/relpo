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
$(PY_META_FILE):	$(PY_RP_PROJ_FILE)
			@$(PY_PX_BIN) run invoke \
				'meta $(PY_RUN_ARGS) -o $(PY_META_FILE) -v'
.PHONY:			rpmetafile
rpmetafile:		$(PY_META_FILE)
			@cat $(PY_META_FILE)

.PHONY:			rppyprojfile
rppyprojfile:		$(PY_PYPROJECT_FILE)
			@head -50 $(PY_PYPROJECT_FILE)

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

# integration tests
.PHONY:			testall
testall:
			@rm -rf $(PY_META_FILE) $(PY_PYPROJECT_FILE)
			@make test $(PY_META_FILE)
			@rm -fr $(MTARG)
			@make $(PY_PYPROJECT_FILE)
