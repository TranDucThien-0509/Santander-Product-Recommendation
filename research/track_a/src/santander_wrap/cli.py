import argparse
import json
from pathlib import Path
from .build import build
from .cards import make_evidence_cards


def main():
    parser=argparse.ArgumentParser(description='Integrate existing Santander outputs without fitting models.')
    sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('build');p.add_argument('--config',required=True)
    p=sub.add_parser('cards-evidence');p.add_argument('--repo',default='.')
    args=parser.parse_args()
    if args.command=='build':
        c=json.loads(Path(args.config).read_text(encoding='utf-8'))
        result=build(c)
        print(json.dumps({k:result[k] for k in ['as_of_month','n_known','n_observed','n_persona_assigned','n_clv','recommendation_rows']},ensure_ascii=False,indent=2))
    else:
        make_evidence_cards(args.repo);print('Generated six evidence cards.')


if __name__=='__main__':main()
